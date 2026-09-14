import re
import requests
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import logging
from config import FEEDS, POLYMARKET_API_URL, HACKER_NEWS_TOP_URL, HACKER_NEWS_ITEM_URL
from storage import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; XenaRealtimeCurator/3.0; +https://github.com/MaximeZoppini/Xena-Newsletter)"
}

# Cache HTTP pour le temps réel (ETag et Last-Modified)
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

def extract_image_url(entry: Any, article_url: str) -> Optional[str]:
    if hasattr(entry, "media_content") and entry.media_content:
        for m in entry.media_content:
            if m.get("url") and "image" in m.get("type", "image"):
                return m["url"]
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get("href") and "image" in enc.get("type", "image"):
                return enc["href"]
    
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=3)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "html.parser")
            og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
            if og and og.get("content"):
                c = og["content"].strip()
                if c.startswith("http"):
                    return c
    except Exception:
        pass
    return None

def fetch_rss_feeds() -> List[Dict[str, Any]]:
    items = []
    for feed_info in FEEDS:
        url = feed_info["url"]
        req_headers = dict(HEADERS)
        
        # Envoi conditionnel ETag / Last-Modified
        if url in FEED_CACHE:
            if FEED_CACHE[url].get("etag"):
                req_headers["If-None-Match"] = FEED_CACHE[url]["etag"]
            if FEED_CACHE[url].get("last_modified"):
                req_headers["If-Modified-Since"] = FEED_CACHE[url]["last_modified"]

        try:
            resp = requests.get(url, headers=req_headers, timeout=6)
            
            # 304 = Aucun changement depuis le dernier check
            if resp.status_code == 304:
                continue

            if resp.status_code == 200:
                # Mise à jour du cache d'en-têtes
                FEED_CACHE[url] = {
                    "etag": resp.headers.get("ETag", ""),
                    "last_modified": resp.headers.get("Last-Modified", "")
                }
                
                parsed = feedparser.parse(resp.content)
                for entry in parsed.entries[:2]:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    if not title or not link:
                        continue
                        
                    if should_skip_title(title):
                        continue
                    
                    raw_summary = entry.get("summary") or entry.get("description", "")
                    summary = clean_html(raw_summary)
                    pub_date = entry.get("published", "") or entry.get("updated", "")
                    image_url = extract_image_url(entry, link)
                    
                    items.append({
                        "id": Storage.generate_id(link, title),
                        "title": title,
                        "url": link,
                        "source": feed_info["name"],
                        "category": feed_info["category"],
                        "known_bias": feed_info["known_bias"],
                        "summary": summary,
                        "image_url": image_url,
                        "published_at": pub_date
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
                        "summary": desc,
                        "image_url": "https://news.ycombinator.com/y18.svg",
                        "published_at": str(data.get("time", ""))
                    })
    except Exception as e:
        logger.debug(f"Erreur fetch Hacker News: {e}")
    return items

def fetch_polymarket() -> List[Dict[str, Any]]:
    items = []
    try:
        resp = requests.get(POLYMARKET_API_URL, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            events = resp.json()
            for ev in events[:2]:
                title = ev.get("title", "").strip()
                if not title:
                    continue
                slug = ev.get("slug", "")
                url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
                markets = ev.get("markets", [])
                image = ev.get("image") or ev.get("icon")
                
                outcomes_summary = []
                volume = ev.get("volume24hr") or ev.get("volume", 0)
                
                for m in markets[:2]:
                    question = m.get("question", "")
                    outcomes = m.get("outcomes", "[]")
                    prices = m.get("outcomePrices", "[]")
                    outcomes_summary.append(f"Question: {question} (Probabilités: {outcomes} -> {prices})")
                
                summary = f"Volume 24h: {volume:.0f} $. " + " | ".join(outcomes_summary)
                
                items.append({
                    "id": Storage.generate_id(url, title),
                    "title": f"[Polymarket] {title}",
                    "url": url,
                    "source": "Polymarket",
                    "category": "prediction_market",
                    "known_bias": "Marché de prédiction probabiliste basé sur des mises financières réelles",
                    "summary": summary,
                    "image_url": image,
                    "published_at": ""
                })
    except Exception as e:
        logger.debug(f"Erreur fetch Polymarket: {e}")
    return items

def get_all_new_candidates(storage: Storage) -> List[Dict[str, Any]]:
    all_candidates = []
    for item in fetch_rss_feeds():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    for item in fetch_hacker_news():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    for item in fetch_polymarket():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    return all_candidates
