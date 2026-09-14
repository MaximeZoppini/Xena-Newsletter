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

MAX_DAILY_POSTS = 4

def run_pipeline_cycle(storage: Storage, analyzer: NewsAnalyzer, dry_run: bool = False):
    logger.info("=== Lancement du cycle de curation éditoriale ===")
    
    # 1. Vérification du quota journalier (Anti-Spam)
    daily_count = storage.count_published_last_24h()
    logger.info(f"Publications effectuées sur les dernières 24h : {daily_count}/{MAX_DAILY_POSTS}")
    if daily_count >= MAX_DAILY_POSTS and not dry_run:
        logger.info("Plafond quotidien de 4 posts atteint. Veille en pause pour préserver la qualité du compte.")
        return

    # 2. Récupération des candidats non encore analysés
    candidates = get_all_new_candidates(storage)
    if not candidates:
        logger.info("Aucune nouvelle information brute détectée.")
        return

    logger.info(f"{len(candidates)} dépêches candidates à évaluer.")

    # 3. Évaluation multi-critères
    qualified_items = []
    
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
            logger.info(f"🎯 ÉLIGIBLE : '{item['title'][:60]}...' (Score {score}/10, Nouveauté {novelty}/10)")
            qualified_items.append((score, item, analysis))
        else:
            reason = analysis.get("rejection_reason") or "Score insuffisant"
            logger.info(f"❌ Rejeté ({score}/10) : '{item['title'][:50]}...' -> {reason}")
            
    if not qualified_items:
        logger.info("Fin du cycle : aucune dépêche n'a franchi le seuil d'exigence (≥ 8.0/10).")
        return

    # 4. Sélection stricte de la MEILLEURE actu du cycle (Top 1 absolu)
    qualified_items.sort(key=lambda x: x[0], reverse=True)
    best_score, best_item, best_analysis = qualified_items[0]
    
    logger.info(f"🏆 PÉPITE RETENUE DU CYCLE : '{best_item['title']}' (Score: {best_score}/10)")
    
    if not dry_run:
        success = notify(best_item, best_analysis)
        if success:
            storage.mark_published(best_item["id"])
            logger.info("Alerte transmise avec succès à l'éditeur sur Telegram.")
    else:
        print("\n" + "="*60)
        print(f"[DRY-RUN TOP 1 RETENU] (Score {best_score}/10)")
        print(f"Source : {best_item['source']}")
        print(f"Titre  : {best_item['title']}")
        print(f"Fait   : {best_analysis.get('factual_core')}")
        print(f"Tweet  :\n{best_analysis.get('tweet_text')}")
        print("="*60 + "\n")

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

    logger.info(f"x-newsletter en veille active (cycle toutes les {POLL_INTERVAL_MINUTES} min, max {MAX_DAILY_POSTS} posts/jour).")
    while True:
        try:
            run_pipeline_cycle(storage, analyzer, dry_run=False)
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle : {e}", exc_info=True)
            
        logger.info(f"Prochain cycle dans {POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(POLL_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
