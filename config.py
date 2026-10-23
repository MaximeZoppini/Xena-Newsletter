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

# Synthèse 12 h : modèle fort, heures locales de publication
GEMINI_SYNTH_MODEL = os.getenv("GEMINI_SYNTH_MODEL", GEMINI_CHAT_MODEL)
GEMINI_SYNTH_THINKING = os.getenv("GEMINI_SYNTH_THINKING", "high")
SYNTHESE_HEURES = [int(h) for h in os.getenv("SYNTHESE_HEURES", "7,19").split(",") if h.strip()]
TIMEZONE = os.getenv("XENA_TIMEZONE", "Europe/Paris")

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

# Flux surveillés : trois thèmes seulement — géopolitique majeure, avancées technologiques, business.
# La notation (analyzer.py) écarte ensuite tout ce qui sort de ces thèmes.
# level : 1 source primaire (annonce officielle, publication, agence d'État), 2 chercheur ou firme reconnue,
# 3 presse sérieuse, 4 réseau social. C'est le point de départ de la confiance, pas la loi.
# watchlist_only : ne garder que les entrées qui citent un composant de l'infra (réglages) ou un langage répandu ; max_items : entrées lues par passage.
def _feed(name, url, category, known_bias, level=3, watchlist_only=False, max_items=2):
    return {"name": name, "url": url, "category": category, "known_bias": known_bias,
            "level": level, "watchlist_only": watchlist_only, "max_items": max_items}


FEEDS = [
    # --- Avancées technologiques et scientifiques
    _feed("Google Research", "https://research.google/blog/rss/", "tech", "Blog officiel de la recherche Google : communication de l'entreprise", level=1),
    _feed("Google DeepMind", "https://deepmind.google/blog/rss.xml", "tech", "Blog officiel de DeepMind : communication de l'entreprise", level=1),
    _feed("OpenAI", "https://openai.com/news/rss.xml", "tech", "Actualités officielles d'OpenAI : communication de l'entreprise", level=1),
    _feed("MIT Technology Review", "https://www.technologyreview.com/feed/", "tech", "Revue du MIT, technologies émergentes et leurs enjeux"),
    _feed("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "tech", "Média tech de référence, focus technique et réglementaire"),
    _feed("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "tech", "Magazine de l'IEEE, ingénierie et technologies"),
    _feed("Quanta Magazine", "https://www.quantamagazine.org/feed/", "tech", "Magazine de vulgarisation scientifique de référence (Fondation Simons)"),
    _feed("Nature", "https://www.nature.com/nature.rss", "tech", "Revue scientifique de référence (articles et actualités)", level=1),
    _feed("Phys.org Quantique", "https://phys.org/rss-feed/physics-news/quantum-physics/", "tech", "Agrégateur de communiqués de recherche en physique quantique"),
    _feed("SpaceNews", "https://spacenews.com/feed/", "tech", "Média spécialisé de l'industrie spatiale"),
    _feed("Teslarati", "https://www.teslarati.com/feed/", "tech", "Média centré sur Tesla et SpaceX, très favorable à Elon Musk"),
    # --- Sécurité : seulement ce qui touche un composant critique
    _feed("CERT-FR Alertes", "https://www.cert.ssi.gouv.fr/alerte/feed/", "securite", "Agence nationale (ANSSI) : alertes de sécurité, source primaire", level=1, watchlist_only=True, max_items=10),
    _feed("CERT-FR Avis", "https://www.cert.ssi.gouv.fr/avis/feed/", "securite", "Agence nationale (ANSSI) : avis de vulnérabilité, source primaire", level=1, watchlist_only=True, max_items=20),
    # --- Géopolitique
    _feed("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "geopolitique", "Service public britannique, international"),
    _feed("Le Monde International", "https://www.lemonde.fr/international/rss_full.xml", "geopolitique", "Quotidien français de référence, rubrique internationale"),
    _feed("Financial Times Monde", "https://www.ft.com/world?format=rss", "geopolitique", "Quotidien économique britannique de référence, international"),
    _feed("New York Times Monde", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "geopolitique", "Quotidien américain de référence, international, centre gauche"),
    _feed("Foreign Policy", "https://foreignpolicy.com/feed/", "geopolitique", "Revue américaine de politique étrangère et d'analyse"),
    _feed("Le Grand Continent", "https://legrandcontinent.eu/fr/feed/", "geopolitique", "Revue européenne de géopolitique, perspective pro-européenne"),
    _feed("Politico Europe", "https://www.politico.eu/feed/", "geopolitique", "Média politique centré sur l'UE et Bruxelles"),
    # --- Business
    _feed("Financial Times Entreprises", "https://www.ft.com/companies?format=rss", "business", "Quotidien économique britannique de référence, entreprises"),
    _feed("The Economist Business", "https://www.economist.com/business/rss.xml", "business", "Hebdomadaire britannique libéral, analyse économique"),
    _feed("New York Times Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml", "business", "Quotidien américain de référence, économie et entreprises"),
    _feed("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "business", "Chaîne économique américaine, marchés et entreprises"),
    _feed("TechCrunch", "https://techcrunch.com/feed/", "business", "Média tech américain axé startups, financements et industrie"),
]

# Langages et runtimes répandus : leurs failles passent le filtre des flux de sécurité même hors de l'infra ;
# l'analyse ne retient ensuite que les failles majeures et avérées.
LANGAGES = ["Golang", "Rust", "Ruby", ".NET", "JavaScript", "TypeScript", "Perl", "Kotlin", "Swift",
            "glibc", "LLVM", "GCC", "V8", "WebAssembly"]

# Catalogue CISA des vulnérabilités exploitées (KEV) : filtré sur les composants critiques
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
HACKER_NEWS_LEVEL = 3

# API Hacker News
HACKER_NEWS_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HACKER_NEWS_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
