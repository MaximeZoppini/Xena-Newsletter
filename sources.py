import re
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import logging
import reglages
from config import CISA_KEV_URL, FEEDS, HACKER_NEWS_TOP_URL, HACKER_NEWS_ITEM_URL
from storage import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; XenaRealtimeCurator/3.0; +https://github.com/MaximeZoppini/Xena-Newsletter)"
}

# Cache HTTP ETag / Last-Modified
FEED_CACHE: Dict[str, Dict[str, str]] = {}

# Mots-clés de rejet automatique sans appel IA
REJECT_KEYWORDS = [
    r"\bj'ai acheté\b", r"\bj'ai testé\b", r"\btest\b", r"\breview\b",
    r"\bbilan\b", r"\bvidéo\b", r"\btwitch\b", r"\bchronique\b",
    r"\bpodcast\b", r"\bopinion\b", r"\btribune\b", r"\bdébrief\b",
    r"\bguide d'achat\b", r"\bbon plan\b", r"\bpromo\b"
]
REJECT_REGEX = re.compile("|".join(REJECT_KEYWORDS), re.IGNORECASE)

def should_skip_title(title: str) -> bool:
    return bool(REJECT_REGEX.search(title))

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())[:1200]

def fetch_rss_feeds(watchlist: Optional[re.Pattern] = None) -> List[Dict[str, Any]]:
    items = []
    for feed_info in FEEDS:
        url = feed_info["url"]
        req_headers = dict(HEADERS)
        
        if url in FEED_CACHE:
            if FEED_CACHE[url].get("etag"):
                req_headers["If-None-Match"] = FEED_CACHE[url]["etag"]
            if FEED_CACHE[url].get("last_modified"):
                req_headers["If-Modified-Since"] = FEED_CACHE[url]["last_modified"]

        try:
            resp = requests.get(url, headers=req_headers, timeout=6)
            if resp.status_code == 304:
                continue

            if resp.status_code == 200:
                FEED_CACHE[url] = {
                    "etag": resp.headers.get("ETag", ""),
                    "last_modified": resp.headers.get("Last-Modified", "")
                }
                
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:feed_info["max_items"]]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    if not title or not link:
                        continue
                        
                    if should_skip_title(title):
                        continue
                    
                    image = ""
                    for media in (entry.get("media_content") or []) + (entry.get("media_thumbnail") or []):
                        if media.get("url"):
                            image = media["url"]
                            break
                    if not image:
                        for enc in entry.get("enclosures") or []:
                            if enc.get("type", "").startswith("image") and enc.get("href"):
                                image = enc["href"]
                                break
                    raw_summary = entry.get("summary") or entry.get("description", "")
                    summary = clean_html(raw_summary)
                    if feed_info["watchlist_only"] and not (watchlist and watchlist.search(f"{title} {summary}")):
                        continue
                    pub_date = entry.get("published", "") or entry.get("updated", "")
                    
                    items.append({
                        "id": Storage.generate_id(link, title),
                        "title": title,
                        "url": link,
                        "source": feed_info["name"],
                        "category": feed_info["category"],
                        "known_bias": feed_info["known_bias"],
                        "source_level": feed_info["level"],
                        "summary": summary,
                        "published_at": pub_date,
                        "image": image
                    })
        except Exception as e:
            logger.debug(f"Erreur légère fetch RSS {feed_info['name']}: {e}")
    return items

def fetch_hacker_news() -> List[Dict[str, Any]]:
    items = []
    try:
        resp = requests.get(HACKER_NEWS_TOP_URL, headers=HEADERS, timeout=5)
        if resp.status_code == 200:
            top_ids = resp.json()[:3]
            for item_id in top_ids:
                item_resp = requests.get(HACKER_NEWS_ITEM_URL.format(item_id=item_id), headers=HEADERS, timeout=4)
                if item_resp.status_code == 200:
                    data = item_resp.json()
                    title = data.get("title", "").strip()
                    if not title or should_skip_title(title):
                        continue
                    url = data.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
                    score = data.get("score", 0)
                    desc = f"Score HN: {score} points. Communauté ingénieurs et chercheurs tech."
                    
                    items.append({
                        "id": Storage.generate_id(url, title),
                        "title": title,
                        "url": url,
                        "source": "Hacker News",
                        "category": "tech_signal",
                        "known_bias": "Agrégateur tech d'ingénieurs et chercheurs",
                        "source_level": 3,
                        "summary": desc,
                        "published_at": str(data.get("time", ""))
                    })
    except Exception as e:
        logger.debug(f"Erreur fetch Hacker News: {e}")
    return items

def fetch_cisa_kev(watchlist: Optional[re.Pattern]) -> List[Dict[str, Any]]:
    """Entrées récentes du catalogue CISA KEV (failles exploitées) qui touchent un composant critique."""
    if not watchlist:
        return []
    req_headers = dict(HEADERS)
    cached = FEED_CACHE.get(CISA_KEV_URL, {})
    if cached.get("etag"):
        req_headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        req_headers["If-Modified-Since"] = cached["last_modified"]
    items = []
    try:
        resp = requests.get(CISA_KEV_URL, headers=req_headers, timeout=15)
        if resp.status_code != 200:
            return []
        FEED_CACHE[CISA_KEV_URL] = {"etag": resp.headers.get("ETag", ""), "last_modified": resp.headers.get("Last-Modified", "")}
        # Seulement les ajouts de la semaine : le catalogue entier n'est pas de l'actualité
        since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400))
        vulns = [v for v in resp.json().get("vulnerabilities", []) if v.get("dateAdded", "") >= since]
        for v in vulns:
            text = f"{v.get('vendorProject', '')} {v.get('product', '')} {v.get('vulnerabilityName', '')}"
            if not watchlist.search(text):
                continue
            title = f"CISA KEV : {v.get('cveID')} — {v.get('vulnerabilityName', '')}"
            url = f"https://nvd.nist.gov/vuln/detail/{v.get('cveID')}"
            items.append({
                "id": Storage.generate_id(url, v.get("cveID", "")),
                "title": title,
                "url": url,
                "source": "CISA KEV",
                "category": "securite",
                "known_bias": "Agence fédérale américaine : faille dont l'exploitation active est confirmée, source primaire",
                "source_level": 1,
                "summary": f"{v.get('shortDescription', '')} Action requise : {v.get('requiredAction', '')} "
                           f"Ajoutée au catalogue le {v.get('dateAdded', '')}, échéance {v.get('dueDate', '')}. "
                           f"Rançongiciel connu : {v.get('knownRansomwareCampaignUse', '')}.",
                "published_at": v.get("dateAdded", ""),
            })
    except Exception as e:
        logger.debug(f"Erreur fetch CISA KEV: {e}")
    return items

def get_all_new_candidates(storage: Storage) -> List[Dict[str, Any]]:
    all_candidates = []
    watchlist = reglages.composants_regex(storage)
    for item in fetch_rss_feeds(watchlist) + fetch_cisa_kev(watchlist):
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    for item in fetch_hacker_news():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    return all_candidates
