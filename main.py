import time
import argparse
import logging
from config import DATABASE_PATH, POLL_INTERVAL_MINUTES
from storage import Storage
from sources import get_all_new_candidates
from analyzer import NewsAnalyzer
from notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def run_pipeline_cycle(storage: Storage, analyzer: NewsAnalyzer, dry_run: bool = False):
    logger.info("=== Lancement du cycle de veille éditoriale ===")
    
    # 1. Récupération des nouveaux candidats
    candidates = get_all_new_candidates(storage)
    if not candidates:
        logger.info("Aucune nouvelle information brute détectée.")
        return

    logger.info(f"{len(candidates)} dépêches candidates à évaluer.")

    # 2. Évaluation multi-critères
    qualified_count = 0
    
    for item in candidates:
        if not dry_run:
            storage.save_article(item)
            
        analysis = analyzer.analyze(item)
        if not analysis:
            continue
            
        score = analysis.get("global_score", 0.0)
        novelty = analysis.get("novelty_scoop", 0)
        
        if not dry_run:
            storage.save_analysis(item["id"], analysis)
            
        # Seuil d'éligibilité : Score global >= 8.0 ET Nouveauté >= 7
        if score >= 8.0 and novelty >= 7:
            logger.info(f"🎯 RETENU : '{item['title'][:60]}...' (Score {score}/10, Nouveauté {novelty}/10)")
            qualified_count += 1
            
            if not dry_run:
                success = notify(item, analysis)
                if success:
                    storage.mark_published(item["id"])
                    time.sleep(1.5) # Pause anti-rate limit Telegram
            else:
                print("\n" + "="*60)
                print(f"[DRY-RUN RETENU] Score {score}/10 (Nouveauté: {novelty}/10)")
                print(f"Source : {item['source']}")
                print(f"Titre  : {item['title']}")
                print(f"Fait   : {analysis.get('factual_core')}")
                print(f"Tweet  :\n{analysis.get('tweet_text')}")
                print("="*60 + "\n")
        else:
            reason = analysis.get("rejection_reason") or "Score insuffisant"
            logger.info(f"❌ Rejeté ({score}/10) : '{item['title'][:50]}...' -> {reason}")
            
    logger.info(f"Cycle terminé. {qualified_count} alertes de haute valeur transmises à l'éditeur.")

def main():
    parser = argparse.ArgumentParser(description="x-newsletter : curateur d'élite impartial")
    parser.add_argument("--test-sources", action="store_true", help="Teste l'ingestion des flux")
    parser.add_argument("--dry-run", action="store_true", help="Exécute un cycle sans envoyer de notification")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle puis quitte")
    args = parser.parse_args()

    storage = Storage(DATABASE_PATH)
    analyzer = NewsAnalyzer()

    if args.test_sources:
        candidates = get_all_new_candidates(storage)
        print(f"Trouvé {len(candidates)} items bruts.")
        return

    if args.dry_run or args.once:
        run_pipeline_cycle(storage, analyzer, dry_run=args.dry_run)
        return

    logger.info(f"x-newsletter en veille active continue (cycle toutes les {POLL_INTERVAL_MINUTES} min, seuil ≥ 8.0/10).")
    while True:
        try:
            run_pipeline_cycle(storage, analyzer, dry_run=False)
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle : {e}", exc_info=True)
            
        logger.info(f"Prochain cycle de veille dans {POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(POLL_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
