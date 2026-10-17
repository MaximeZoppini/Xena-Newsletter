import argparse
import logging
import time

from analyzer import NewsAnalyzer
from briefing import Briefer
from config import DATABASE_PATH, MIN_INTEREST_SCORE, POLL_INTERVAL_SECONDS, WEB_HOST, WEB_PORT
from sources import get_all_new_candidates
from storage import Storage
from web import start_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def run_pipeline_cycle(storage: Storage, analyzer: NewsAnalyzer, briefer: Briefer, dry_run: bool = False):
    """
    Veille continue : récupère les nouvelles publications, les fait noter par l'IA,
    et prépare la fiche de lecture complète des news importantes.
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
        if dry_run:
            print(f"[DRY-RUN] '{item['title'][:60]}' -> {score}/10 | {analysis.get('titre_fr', '')}")
            continue

        storage.save_analysis(item["id"], analysis)
        logger.info(f"📥 '{item['title'][:50]}...' -> {score}/10")
        if score >= MIN_INTEREST_SCORE:
            # Fiche + version audio courte prêtes d'avance : le flash « Ce que j'ai raté » démarre sans attente
            briefer.get_or_create_brief(item["id"])
            briefer.get_or_create_short_audio(item["id"])


def main():
    parser = argparse.ArgumentParser(description="Xena : veille d'actualité personnelle")
    parser.add_argument("--test-sources", action="store_true", help="Teste l'ingestion des flux")
    parser.add_argument("--dry-run", action="store_true", help="Exécute un cycle sans rien enregistrer")
    parser.add_argument("--backfill-days", type=int, metavar="N",
                        help="Prépare fiches et versions audio courtes des news importantes des N derniers jours puis quitte")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle puis quitte")
    args = parser.parse_args()

    storage = Storage(DATABASE_PATH)
    analyzer = NewsAnalyzer(storage=storage)
    briefer = Briefer(storage)

    if args.test_sources:
        candidates = get_all_new_candidates(storage)
        print(f"Trouvé {len(candidates)} items bruts.")
        return

    if args.backfill_days:
        since = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - args.backfill_days * 86400))
        rows = [r for r in storage.list_articles(min_score=MIN_INTEREST_SCORE, limit=1000)
                if r["ingested_at"] >= since]
        logger.info(f"Préparation de {len(rows)} fiche(s)...")
        for r in rows:
            briefer.get_or_create_brief(r["id"])
            briefer.get_or_create_short_audio(r["id"])
        return

    if args.dry_run or args.once:
        run_pipeline_cycle(storage, analyzer, briefer, dry_run=args.dry_run)
        return

    start_web_server(storage, briefer, host=WEB_HOST, port=WEB_PORT)
    logger.info(f"🚀 Xena active : veille toutes les {POLL_INTERVAL_SECONDS}s, site sur http://{WEB_HOST}:{WEB_PORT}")

    while True:
        try:
            run_pipeline_cycle(storage, analyzer, briefer)
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle : {e}", exc_info=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
