import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Clés API et Webhooks
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# TypeSafe AI (Modèle Jev - Filtrage Étage 1 & Scoring d'impartialité)
TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")
TYPESAFE_MODEL = os.getenv("TYPESAFE_MODEL", "jev-latest")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Base de données & Paramètres
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "x_newsletter.db"))
CARDS_DIR = os.getenv("CARDS_DIR", str(BASE_DIR / "data" / "cards"))

# Veille en temps réel (scan toutes les 60s avec ETag caching)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Seuil d'admissibilité éditoriale (Faable recommande ≥ 7.5 pour attraper les vraies enquêtes de fond)
MIN_INTEREST_SCORE = float(os.getenv("MIN_INTEREST_SCORE", "7.5"))

# Publication quotidienne (12h00 par défaut = tous les midis)
PUBLISH_HOUR = int(os.getenv("PUBLISH_HOUR", "12"))
PUBLISH_MINUTE = int(os.getenv("PUBLISH_MINUTE", "0"))

# Flux d'investigation et tech surveillés
FEEDS = [
    {
        "name": "Mediapart",
        "url": "https://www.mediapart.fr/articles/feed",
        "category": "investigation",
        "known_bias": "Média d'investigation indépendant, critique du pouvoir"
    },
    {
        "name": "Disclose",
        "url": "https://disclose.ngo/feed",
        "category": "investigation",
        "known_bias": "ONG de journalisme d'investigation, axé droits humains et environnement"
    },
    {
        "name": "Reporterre",
        "url": "https://reporterre.net/spip.php?page=backend",
        "category": "ecologie",
        "known_bias": "Média indépendant écologiste"
    },
    {
        "name": "ProPublica",
        "url": "https://www.propublica.org/feeds/propublica/main",
        "category": "investigation",
        "known_bias": "Journalisme d'investigation à but non lucratif américain"
    },
    {
        "name": "404 Media",
        "url": "https://www.404media.co/rss/",
        "category": "tech_cyber",
        "known_bias": "Média tech indépendant axé surveillance, cyber et hacking"
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "tech",
        "known_bias": "Média tech de référence, focus réglementaire et technique"
    },
    {
        "name": "BleepingComputer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "category": "cyber",
        "known_bias": "Spécialisé cybersécurité, vulnérabilités et menaces"
    },
    {
        "name": "Alignment Forum",
        "url": "https://www.alignmentforum.org/feed.xml",
        "category": "ai_safety",
        "known_bias": "Plateforme de recherche & whistleblowing en sécurité AGI (DeepMind, Anthropic, OpenAI)"
    },
    {
        "name": "The Guardian Technology",
        "url": "https://www.theguardian.com/technology/rss",
        "category": "tech_investigation",
        "known_bias": "Média international de référence, enquêtes Big Tech et IA"
    },
    {
        "name": "EFF",
        "url": "https://www.eff.org/rss/updates.xml",
        "category": "digital_rights",
        "known_bias": "ONG pionnière sur les libertés numériques, surveillance et chiffrement"
    }
]

# API Hacker News
HACKER_NEWS_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HACKER_NEWS_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
