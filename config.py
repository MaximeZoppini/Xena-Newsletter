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

# Modèles : analyse rapide (Flash), conversation (le meilleur Pro), voix (TTS)
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-pro-latest")
GEMINI_CHAT_THINKING = os.getenv("GEMINI_CHAT_THINKING", "low")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")

# Base de données & fichiers générés
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "x_newsletter.db"))
AUDIO_DIR = os.getenv("AUDIO_DIR", str(BASE_DIR / "data" / "audio"))
STATIC_DIR = str(BASE_DIR / "static")

# Veille en temps réel (scan toutes les 60s avec ETag caching)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Score à partir duquel une news est "importante" : fiche complète générée et affichée par défaut
MIN_INTEREST_SCORE = float(os.getenv("MIN_INTEREST_SCORE", "7"))

# Site web : écoute en local uniquement, exposé sur le tailnet via `tailscale serve`
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# Flux surveillés : d'abord les avancées tech & science, puis l'investigation
def _feed(name, url, category, known_bias):
    return {"name": name, "url": url, "category": category, "known_bias": known_bias}


FEEDS = [
    _feed("The Verge", "https://www.theverge.com/rss/index.xml", "tech", "Média tech grand public américain, produits et industrie"),
    _feed("TechCrunch", "https://techcrunch.com/feed/", "tech", "Média tech américain axé startups, financements et lancements"),
    _feed("MIT Technology Review", "https://www.technologyreview.com/feed/", "science_tech", "Revue du MIT, technologies émergentes et leurs enjeux"),
    _feed("Electrek", "https://electrek.co/feed/", "mobilite", "Média spécialisé véhicules électriques, Tesla et énergie, plutôt enthousiaste"),
    _feed("Google Blog", "https://blog.google/rss/", "annonce_officielle", "Blog officiel de Google : communication de l'entreprise"),
    _feed("Google Research", "https://research.google/blog/rss/", "recherche", "Blog officiel de la recherche Google : communication de l'entreprise"),
    _feed("Google DeepMind", "https://deepmind.google/blog/rss.xml", "recherche", "Blog officiel de DeepMind : communication de l'entreprise"),
    _feed("OpenAI", "https://openai.com/news/rss.xml", "annonce_officielle", "Actualités officielles d'OpenAI : communication de l'entreprise"),
    _feed("Quanta Magazine", "https://www.quantamagazine.org/feed/", "science", "Magazine de vulgarisation scientifique de référence (Fondation Simons)"),
    _feed("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "ingenierie", "Magazine de l'IEEE, ingénierie et technologies"),
    _feed("Nature", "https://www.nature.com/nature.rss", "science", "Revue scientifique de référence (articles et actualités)"),
    _feed("SpaceNews", "https://spacenews.com/feed/", "spatial", "Média spécialisé de l'industrie spatiale"),
    _feed("Numerama", "https://www.numerama.com/feed/", "tech", "Média tech et sciences français"),
    _feed("Frandroid", "https://www.frandroid.com/feed", "tech", "Média tech français, produits et mobilité électrique"),
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
