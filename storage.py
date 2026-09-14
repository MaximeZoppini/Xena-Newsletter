import sqlite3
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

class Storage:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    url TEXT UNIQUE,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    raw_summary TEXT,
                    published_at TEXT,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    article_id TEXT PRIMARY KEY,
                    systemic_impact INTEGER,
                    novelty_scoop INTEGER,
                    evidence_quality INTEGER,
                    global_score REAL,
                    factual_core TEXT,
                    framing_detected TEXT,
                    counter_view TEXT,
                    tweet_text TEXT,
                    published_to_telegram INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles(id)
                )
            """)
            conn.commit()

    @staticmethod
    def generate_id(url: str, title: str) -> str:
        key = f"{url.strip().lower()}|{title.strip().lower()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def is_seen(self, article_id: str, url: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM articles WHERE id = ? OR url = ?", (article_id, url))
            return cur.fetchone() is not None

    def save_article(self, article: Dict[str, Any]) -> bool:
        art_id = article.get("id") or self.generate_id(article["url"], article["title"])
        with self._get_connection() as conn:
            try:
                conn.execute("""
                    INSERT INTO articles (id, url, title, source, category, raw_summary, published_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    art_id,
                    article["url"],
                    article["title"],
                    article["source"],
                    article.get("category", "general"),
                    article.get("summary", ""),
                    article.get("published_at", ""),
                    "pending"
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def save_analysis(self, article_id: str, analysis: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO analyses (
                    article_id, systemic_impact, novelty_scoop, evidence_quality, global_score,
                    factual_core, framing_detected, counter_view, tweet_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article_id,
                analysis.get("systemic_impact", 0),
                analysis.get("novelty_scoop", 0),
                analysis.get("evidence_quality", 0),
                analysis.get("global_score", 0.0),
                analysis.get("factual_core", ""),
                analysis.get("framing_detected", ""),
                analysis.get("counter_view", ""),
                analysis.get("tweet_text", "")
            ))
            score = analysis.get("global_score", 0.0)
            status = "eligible" if score >= 8.0 and analysis.get("novelty_scoop", 0) >= 7 else "rejected"
            conn.execute("UPDATE articles SET status = ? WHERE id = ?", (status, article_id))
            conn.commit()

    def mark_published(self, article_id: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE analyses SET published_to_telegram = 1 WHERE article_id = ?", (article_id,))
            conn.execute("UPDATE articles SET status = 'published' WHERE id = ?", (article_id,))
            conn.commit()

    def count_published_last_24h(self) -> int:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) as count FROM analyses 
                WHERE published_to_telegram = 1 
                AND datetime(created_at) >= datetime('now', '-1 day')
            """)
            row = cur.fetchone()
            return row["count"] if row else 0
