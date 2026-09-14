import time
import argparse
import logging
from config import DATABASE_PATH, POLL_INTERVAL_MINUTES, MIN_INTEREST_SCORE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from storage import Storage
from sources import get_all_new_candidates
from analyzer import NewsAnalyzer
from notifier import notify, send_telegram_notification, send_discord_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

def run_pipeline_once(storage: Storage, analyzer: NewsAnalyzer, dry_run: bool = False):
    logger.info("Démarrage du cycle de veille...")
    candidates = get_all_new_candidates(storage)
    
    if not candidates:
        logger.info("Aucune nouvelle information détectée lors de ce cycle.")
        return

    logger.info(f"{len(candidates)} nouvelles informations à analyser.")
    
    processed = 0
    for item in candidates:
        logger.info(f"Analyse de : {item['title']} ({item['source']})")
        
        if not dry_run:
            storage.save_article(item)
            
        analysis = analyzer.analyze(item)
        if not analysis:
            continue
            
        score = analysis.get("interest_score", 0)
        logger.info(f"-> Score: {score}/10 | Biais: {analysis.get('framing_bias')}")
        
        if not dry_run:
            storage.save_analysis(item["id"], analysis)
            
        if score >= MIN_INTEREST_SCORE:
            logger.info(f"✨ Retenu pour publication (Score {score} >= {MIN_INTEREST_SCORE})")
            if not dry_run:
                notify(item, analysis)
                time.sleep(2)
            else:
                print("\n" + "="*50)
                print(f"[DRY-RUN TWEET RETENU] ({item['source']})")
                print(f"Fait brut : {analysis.get('factual_core')}")
                print(f"Biais     : {analysis.get('framing_bias')}")
                print(f"Tweet     :\n{analysis.get('tweet_text')}")
                print("="*50 + "\n")
                
            processed += 1
            if dry_run and processed >= 3:
                break

    logger.info(f"Cycle terminé. {processed} alertes traitées.")

def main():
    parser = argparse.ArgumentParser(description="x-newsletter : veille impartiale & curateur X/Telegram/Discord")
    parser.add_argument("--test-sources", action="store_true", help="Teste l'ingestion des flux sans analyse")
    parser.add_argument("--test-telegram", action="store_true", help="Envoie un message de test sur Telegram")
    parser.add_argument("--test-discord", action="store_true", help="Envoie un message de test au Webhook Discord")
    parser.add_argument("--dry-run", action="store_true", help="Exécute un cycle sans enregistrer ni envoyer de notification")
    parser.add_argument("--once", action="store_true", help="Exécute un seul cycle puis quitte")
    args = parser.parse_args()

    storage = Storage(DATABASE_PATH)
    analyzer = NewsAnalyzer()

    if args.test_sources:
        print("🔍 Test d'ingestion des sources...")
        candidates = get_all_new_candidates(storage)
        print(f"Trouvé {len(candidates)} items au total :\n")
        for i, it in enumerate(candidates[:10], 1):
            print(f"{i}. [{it['source']} - {it['category']}] {it['title']}")
            print(f"   URL: {it['url']}")
            print(f"   Contexte: {it['known_bias']}")
            print(f"   Extrait: {it['summary'][:120]}...\n")
        return

    sample_item = {
        "title": "Enquête : Révélations sur l'utilisation des données privées dans la tech",
        "url": "https://www.mediapart.fr",
        "source": "Mediapart",
        "known_bias": "Investigation indépendante"
    }
    sample_analysis = {
        "factual_core": "Une fuite de documents internes révèle le partage non consenti de métadonnées utilisateurs vers des courtiers tiers.",
        "framing_bias": "Angle d'investigation axé sur la protection de la vie privée et la régulation des GAFAM.",
        "interest_score": 9,
        "tweet_text": "🚨 Tech : Une fuite de documents confirme le partage massif de métadonnées utilisateurs vers des data brokers sans consentement explicite.\n\n🔗 https://www.mediapart.fr"
    }

    if args.test_telegram:
        print("📨 Envoi d'un message test sur Telegram...")
        success = send_telegram_notification(sample_item, sample_analysis)
        if success:
            print("✅ Test Telegram réussi !")
        else:
            print("❌ Échec Telegram (vérifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans .env)")
        return

    if args.test_discord:
        print("📨 Envoi d'un message test sur Discord...")
        success = send_discord_notification(sample_item, sample_analysis)
        if success:
            print("✅ Test Discord réussi !")
        else:
            print("❌ Échec Discord (vérifie DISCORD_WEBHOOK_URL dans .env)")
        return

    if args.dry_run or args.once:
        run_pipeline_once(storage, analyzer, dry_run=args.dry_run)
        return

    logger.info(f"x-newsletter démarré en mode continu (intervalle: {POLL_INTERVAL_MINUTES} min).")
    while True:
        try:
            run_pipeline_once(storage, analyzer, dry_run=False)
        except Exception as e:
            logger.error(f"Erreur inattendue dans la boucle principale: {e}", exc_info=True)
        
        logger.info(f"En veille pour {POLL_INTERVAL_MINUTES} minutes...")
        time.sleep(POLL_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()
