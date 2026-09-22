import time
import datetime
import argparse
import logging
from config import DATABASE_PATH, POLL_INTERVAL_SECONDS, MIN_INTEREST_SCORE, PUBLISH_HOUR, PUBLISH_MINUTE
from storage import Storage
from sources import get_all_new_candidates
from analyzer import NewsAnalyzer
from notifier import notify, process_telegram_updates

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def run_pipeline_cycle(storage: Storage, analyzer: NewsAnalyzer, dry_run: bool = False):
    """
    Veille continue : récupère tous les nouveaux flux, les fait analyser par Gemini
    et les archive en base de données sans envoyer de notification immédiate.
    """
    candidates = get_all_new_candidates(storage)
    if not candidates:
        return

    logger.info(f"⚡ [VEILLE] {len(candidates)} nouvelle(s) publication(s) détectée(s) !")

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
            
        if dry_run:
            print(f"[DRY-RUN] '{item['title'][:50]}...' -> Score {score}/10 (Scoop {novelty}/10)")
        else:
            logger.info(f"📥 [ARCHIVÉ EN DB] '{item['title'][:50]}...' -> Score {score}/10 (Scoop {novelty}/10)")

def check_and_publish_daily_best(storage: Storage, force: bool = False, dry_run: bool = False) -> bool:
    """
    À 12h00 chaque jour, sélectionne le meilleur article parmi ceux archivés et publie un unique post sur Telegram.
    """
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    last_post_date = storage.get_state("last_daily_post_date")

    if not force:
        # On ne publie qu'à partir de l'heure programmée (12h par défaut)
        if now.hour < PUBLISH_HOUR:
            return False
        # Un seul post par jour : si déjà publié aujourd'hui, on passe
        if last_post_date == today_str:
            return False

    logger.info(f"🏆 [DAILY DISPATCH] Recherche du meilleur scoop du jour (seuil >= {MIN_INTEREST_SCORE})...")
    candidate = storage.get_daily_best_candidate(min_score=MIN_INTEREST_SCORE, max_age_hours=36)
    if not candidate:
        logger.info("ℹ️ [DAILY DISPATCH] Aucun article marquant trouvé pour aujourd'hui.")
        if not dry_run and not force:
            storage.set_state("last_daily_post_date", today_str)
        return False

    item, analysis = candidate
    score = analysis.get("global_score", 0.0)
    logger.info(f"🌟 [DAILY SELECTION RETENU] '{item['title']}' (Score: {score}/10)")

    if dry_run:
        print("\n" + "="*60)
        print(f"[DRY-RUN DAILY BEST] Score {score}/10")
        print(f"Source : {item['source']}")
        print(f"Titre  : {item['title']}")
        print(f"Fait   : {analysis.get('factual_core')}")
        print(f"Tweet  :\n{analysis.get('tweet_text')}")
        print("="*60 + "\n")
        return True

    success = notify(item, analysis)
    if success:
        storage.mark_published(item["id"])
        storage.set_state("last_daily_post_date", today_str)
        logger.info(f"✅ [POST DU MIDI] Scoop quotidien de 12h00 envoyé avec succès sur Telegram !")
        return True
    else:
        logger.error(f"❌ [POST DU MIDI] Échec lors de l'envoi Telegram du post quotidien.")
        return False

from dashboard import start_dashboard_server

def main():
    parser = argparse.ArgumentParser(description="Xena : IA d'investigation et curation quotidienne")
    parser.add_argument("--test-sources", action="store_true", help="Teste l'ingestion des flux")
    parser.add_argument("--dry-run", action="store_true", help="Exécute un cycle sans envoyer de notification")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle puis quitte")
    parser.add_argument("--publish-now", action="store_true", help="Publie immédiatement le meilleur article du jour sur Telegram")
    args = parser.parse_args()

    storage = Storage(DATABASE_PATH)
    analyzer = NewsAnalyzer(storage=storage)

    if args.test_sources:
        candidates = get_all_new_candidates(storage)
        print(f"Trouvé {len(candidates)} items bruts.")
        return

    if args.publish_now:
        check_and_publish_daily_best(storage, force=True, dry_run=False)
        return

    if args.dry_run or args.once:
        run_pipeline_cycle(storage, analyzer, dry_run=args.dry_run)
        check_and_publish_daily_best(storage, force=True, dry_run=args.dry_run)
        return

    # Démarrage du serveur web de télémétrie hybride (Port 8080)
    try:
        start_dashboard_server(storage, host="0.0.0.0", port=8080)
    except Exception as e:
        logger.warning(f"Impossible de démarrer le dashboard web : {e}")

    logger.info(f"🚀 Xena active : Veille continue (toutes les {POLL_INTERVAL_SECONDS}s), Post quotidien à {PUBLISH_HOUR}h00, Dashboard http://0.0.0.0:8080, Telegram polling 2s.")
    tg_offset = 0
    last_pipeline_run = 0.0
    while True:
        try:
            # 1. Écoute Telegram en continu (Ghostwriter tweet replies & feedback)
            tg_offset = process_telegram_updates(storage, analyzer, tg_offset)

            # 2. Vérification de l'heure du post quotidien (12h00)
            check_and_publish_daily_best(storage)

            # 3. Cycle de veille et archivage en DB
            now = time.time()
            if now - last_pipeline_run >= POLL_INTERVAL_SECONDS:
                run_pipeline_cycle(storage, analyzer, dry_run=False)
                last_pipeline_run = now
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle : {e}", exc_info=True)
            
        time.sleep(2)

if __name__ == "__main__":
    main()


