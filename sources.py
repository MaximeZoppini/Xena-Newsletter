import requests
import feedparser
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import logging
from config import FEEDS, POLYMARKET_API_URL, HACKER_NEWS_TOP_URL, HACKER_NEWS_ITEM_URL
from storage import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sources")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; XNewsletterBot/1.0; +https://github.com/)"
}

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())[:1200]

def fetch_rss_feeds() -> List[Dict[str, Any]]:
    items = []
    for feed_info in FEEDS:
        try:
            logger.info(f"Fetching RSS: {feed_info['name']}")
            resp = requests.get(feed_info["url"], headers=HEADERS, timeout=10)
            parsed = feedparser.parse(resp.content)
            
            for entry in parsed.entries[:5]: # Max 5 derniers par flux
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                if not title or not url:
                    continue
                
                raw_summary = entry.get("summary") or entry.get("description", "")
                summary = clean_html(raw_summary)
                pub_date = entry.get("published", "") or entry.get("updated", "")
                
                items.append({
                    "id": Storage.generate_id(url, title),
                    "title": title,
                    "url": url,
                    "source": feed_info["name"],
                    "category": feed_info["category"],
                    "known_bias": feed_info["known_bias"],
                    "summary": summary,
                    "published_at": pub_date
                })
        except Exception as e:
            logger.warning(f"Failed to fetch {feed_info['name']}: {e}")
    return items

def fetch_hacker_news() -> List[Dict[str, Any]]:
    items = []
    try:
        logger.info("Fetching Hacker News Top Stories")
        resp = requests.get(HACKER_NEWS_TOP_URL, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            top_ids = resp.json()[:8] # Top 8
            for item_id in top_ids:
                item_resp = requests.get(HACKER_NEWS_ITEM_URL.format(item_id=item_id), headers=HEADERS, timeout=5)
                if item_resp.status_code == 200:
                    data = item_resp.json()
                    url = data.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
                    title = data.get("title", "").strip()
                    score = data.get("score", 0)
                    desc = f"Score HN: {score} points. Type: tech/discussion."
                    
                    items.append({
                        "id": Storage.generate_id(url, title),
                        "title": title,
                        "url": url,
                        "source": "Hacker News",
                        "category": "tech_signal",
                        "known_bias": "Agrégateur tech & startups, orienté communauté hacker/ingénierie",
                        "summary": desc,
                        "published_at": str(data.get("time", ""))
                    })
    except Exception as e:
        logger.warning(f"Failed to fetch Hacker News: {e}")
    return items

def fetch_polymarket() -> List[Dict[str, Any]]:
    items = []
    try:
        logger.info("Fetching Polymarket Trending Events")
        resp = requests.get(POLYMARKET_API_URL, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            events = resp.json()
            for ev in events[:6]:
                title = ev.get("title", "").strip()
                slug = ev.get("slug", "")
                url = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
                markets = ev.get("markets", [])
                
                outcomes_summary = []
                volume = ev.get("volume24hr") or ev.get("volume", 0)
                
                for m in markets[:2]:
                    question = m.get("question", "")
                    outcomes = m.get("outcomes", "[]")
                    prices = m.get("outcomePrices", "[]")
                    outcomes_summary.append(f"Marché: {question} (Cotes: {outcomes} -> {prices})")
                
                summary = f"Volume 24h: {volume:.0f} $. " + " | ".join(outcomes_summary)
                
                items.append({
                    "id": Storage.generate_id(url, title),
                    "title": f"[Polymarket] {title}",
                    "url": url,
                    "source": "Polymarket",
                    "category": "prediction_market",
                    "known_bias": "Marché de prédiction probabiliste basé sur des mises financières réelles",
                    "summary": summary,
                    "published_at": ""
                })
    except Exception as e:
        logger.warning(f"Failed to fetch Polymarket: {e}")
    return items

def get_all_new_candidates(storage: Storage) -> List[Dict[str, Any]]:
    all_candidates = []
    
    # 1. RSS Feeds
    for item in fetch_rss_feeds():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    # 2. Hacker News
    for item in fetch_hacker_news():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    # 3. Polymarket
    for item in fetch_polymarket():
        if not storage.is_seen(item["id"], item["url"]):
            all_candidates.append(item)
            
    logger.info(f"Total novel candidates found: {len(all_candidates)}")
    return all_candidates
