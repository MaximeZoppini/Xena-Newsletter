import argparse
import logging
import time
from typing import Optional

from alertes import Alerter
from analyzer import NewsAnalyzer
import todo
from briefing import Briefer
from dossiers import Threader
from config import FEEDS, DATABASE_PATH, MIN_INTEREST_SCORE, POLL_INTERVAL_SECONDS, WEB_HOST, WEB_PORT
from sources import get_all_new_candidates
from storage import Storage
from synthese import Synthesizer
from web import start_web_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")


def run_pipeline_cycle(storage: Storage, analyzer: NewsAnalyzer, briefer: Briefer, threader: Threader,
                       alerter: Optional[Alerter] = None, dry_run: bool = False):
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
            threader.thread(item["id"])
            if alerter:
                try:
                    alerter.consider(item["id"])
                except Exception as e:
                    logger.error(f"Décision de push impossible : {e}", exc_info=True)
            # Fiche + version audio courte prêtes d'avance : le flash « Ce que j'ai raté » démarre sans attente
            briefer.get_or_create_brief(item["id"])
            briefer.ensure_image(item["id"])
            briefer.get_or_create_short_audio(item["id"])


def rescore(storage: Storage, analyzer: NewsAnalyzer, briefer: Briefer, threader: Threader, days: int):
    """Applique la grille de notation actuelle aux articles déjà en base."""
    feeds = {f["name"]: f for f in FEEDS}
    rows = storage.list_recent(min_score=0.0, hours=days * 24, limit=5000)
    logger.info(f"Nouvelle notation de {len(rows)} article(s)...")
    for r in rows:
        item = {"id": r["id"], "title": r["title"], "url": r["url"], "source": r["source"],
                "summary": r["raw_summary"] or "", "published_at": r["published_at"] or "",
                "known_bias": feeds.get(r["source"], {}).get("known_bias", "Non précisé"),
                "source_level": feeds.get(r["source"], {}).get("level", 3)}
        analysis = analyzer.analyze(item)
        if not analysis:
            continue
        storage.save_analysis(r["id"], analysis)
        if analysis.get("global_score", 0.0) >= MIN_INTEREST_SCORE:
            threader.thread(r["id"])
            briefer.get_or_create_brief(r["id"])
            briefer.ensure_image(r["id"])
            briefer.get_or_create_short_audio(r["id"])
        logger.info(f"{analysis.get('global_score', 0.0):>4} | {analysis.get('titre_fr') or r['title']}")


def main():
    parser = argparse.ArgumentParser(description="Xena : veille d'actualité personnelle")
    parser.add_argument("--test-sources", action="store_true", help="Teste l'ingestion des flux")
    parser.add_argument("--dry-run", action="store_true", help="Exécute un cycle sans rien enregistrer")
    parser.add_argument("--backfill-days", type=int, metavar="N",
                        help="Prépare fiches et versions audio courtes des news importantes des N derniers jours puis quitte")
    parser.add_argument("--rescore-days", type=int, metavar="N",
                        help="Re-note les articles des N derniers jours avec la grille actuelle puis quitte")
    parser.add_argument("--synthese", action="store_true", help="Produit une synthèse 12 h maintenant puis quitte")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle puis quitte")
    args = parser.parse_args()

    storage = Storage(DATABASE_PATH)
    analyzer = NewsAnalyzer(storage=storage)
    briefer = Briefer(storage)
    threader = Threader(storage)
    synthesizer = Synthesizer(storage)
    alerter = Alerter(storage)

    if args.test_sources:
        candidates = get_all_new_candidates(storage)
        print(f"Trouvé {len(candidates)} items bruts.")
        return

    if args.synthese:
        synthesizer.run()
        return

    if args.rescore_days:
        rescore(storage, analyzer, briefer, threader, args.rescore_days)
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
        run_pipeline_cycle(storage, analyzer, briefer, threader, dry_run=args.dry_run)
        return

    start_web_server(storage, briefer, alerter, host=WEB_HOST, port=WEB_PORT)
    logger.info(f"🚀 Xena active : veille toutes les {POLL_INTERVAL_SECONDS}s, site sur http://{WEB_HOST}:{WEB_PORT}")

    try:
        todo.initialiser()
    except Exception as e:
        logger.error(f"To-do : {e}", exc_info=True)

    # Images manquantes des news importantes des dernières 24 h
    try:
        for r in storage.list_recent(min_score=MIN_INTEREST_SCORE, hours=24, limit=200):
            if not r.get("image_url") and not r.get("image_checked"):
                briefer.ensure_image(r["id"])
    except Exception as e:
        logger.error(f"Rattrapage des images : {e}", exc_info=True)

    # News importantes des dernières 24 h arrivées avant les dossiers (ou pendant un redémarrage) : rangées une fois
    try:
        threader.catch_up(hours=24)
    except Exception as e:
        logger.error(f"Rangement initial en dossiers : {e}", exc_info=True)

    while True:
        try:
            run_pipeline_cycle(storage, analyzer, briefer, threader, alerter)
            synthesizer.maybe_run()
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle : {e}", exc_info=True)
        try:
            todo.initialiser()  # droits des fichiers pour l'agent Agenda, copie de secours
        except Exception as e:
            logger.error(f"To-do : {e}", exc_info=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
