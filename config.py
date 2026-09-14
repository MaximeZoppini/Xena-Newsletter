import os
from pathlib import Path
from dotenv import load_dotenv

# Charger le fichier .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Clés API et Webhooks
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Base de données & Paramètres
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "x_newsletter.db"))

# Veille en temps réel (intervalle en secondes : 60s pour réactivité immédiate sans bannissement IP)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
MIN_INTEREST_SCORE = int(os.getenv("MIN_INTEREST_SCORE", "8"))

# Liste des flux RSS et sources surveillées
FEEDS = [
    {
        "name": "Mediapart",
        "url": "https://www.mediapart.fr/articles/feed",
        "category": "investigation",
        "known_bias": "Média d'investigation indépendant, orientation gauche / critique du pouvoir"
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
        "known_bias": "Média tech indépendant fondé par d'anciens journalistes de Vice/Motherboard"
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "tech",
        "known_bias": "Média tech de référence, focus technique et réglementaire"
    },
    {
        "name": "BleepingComputer",
        "url": "https://www.bleepingcomputer.com/feed/",
        "category": "cyber",
        "known_bias": "Spécialisé cybersécurité, failles et menaces"
    }
]

# API Polymarket
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/events?limit=10&active=true&closed=false&order=volume24hr&ascending=false"

# API Hacker News
HACKER_NEWS_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HACKER_NEWS_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
