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
                    source_quote TEXT,
                    tweet_text TEXT,
                    published_to_telegram INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles(id)
                )
            """)
            # Table de feedback éditorial (pour apprentissage et calibration future)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS editorial_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    action TEXT NOT NULL, -- 'tweeted', 'rejected', 'modified'
                    tweet_text TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Table d'état de l'application (ex: date du dernier post quotidien)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

            # Migrations douces pour les colonnes supplémentaires
            try:
                conn.execute("ALTER TABLE analyses ADD COLUMN target_domain TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE analyses ADD COLUMN chosen_style TEXT")
            except sqlite3.OperationalError:
                pass
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
                    factual_core, framing_detected, counter_view, source_quote, tweet_text,
                    target_domain, chosen_style
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article_id,
                analysis.get("systemic_impact", 0),
                analysis.get("novelty_scoop", 0),
                analysis.get("evidence_quality", 0),
                analysis.get("global_score", 0.0),
                analysis.get("factual_core", ""),
                analysis.get("framing_detected", ""),
                analysis.get("counter_view", ""),
                analysis.get("source_quote", ""),
                analysis.get("tweet_text", ""),
                analysis.get("target_domain", ""),
                analysis.get("chosen_style", "")
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

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM app_state WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_state(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO app_state (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            conn.commit()

    def get_daily_best_candidate(self, min_score: float = 7.0, max_age_hours: int = 36) -> Optional[tuple]:
        """
        Sélectionne le meilleur scoop inédit des dernières heures :
        Trié par meilleur global_score, puis plus récent (ingested_at).
        """
        import urllib.parse
        with self._get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT 
                    a.id, a.url, a.title, a.source, a.category, a.raw_summary, a.published_at, a.ingested_at,
                    an.global_score, an.systemic_impact, an.novelty_scoop, an.evidence_quality,
                    an.factual_core, an.framing_detected, an.counter_view, an.source_quote, an.tweet_text,
                    an.target_domain, an.chosen_style
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                WHERE an.published_to_telegram = 0
                  AND an.global_score >= ?
                  AND datetime(a.ingested_at) >= datetime('now', ?)
                ORDER BY an.global_score DESC, a.ingested_at DESC
                LIMIT 1
            """
            cur.execute(query, (min_score, f"-{max_age_hours} hours"))
            row = cur.fetchone()

            # Fallback : si aucun article n'atteint min_score dans la fenêtre, prendre le meilleur >= 6.0
            if not row and min_score > 6.0:
                cur.execute(query, (6.0, f"-{max_age_hours} hours"))
                row = cur.fetchone()

            if not row:
                return None

            item = {
                "id": row["id"],
                "url": row["url"],
                "title": row["title"],
                "source": row["source"],
                "category": row["category"],
                "summary": row["raw_summary"],
                "published_at": row["published_at"],
                "ingested_at": row["ingested_at"]
            }

            target_domain = row["target_domain"]
            if not target_domain and row["url"]:
                try:
                    target_domain = urllib.parse.urlparse(row["url"]).netloc.replace("www.", "")
                except Exception:
                    target_domain = ""

            analysis = {
                "global_score": row["global_score"],
                "systemic_impact": row["systemic_impact"],
                "novelty_scoop": row["novelty_scoop"],
                "evidence_quality": row["evidence_quality"],
                "factual_core": row["factual_core"],
                "framing_detected": row["framing_detected"],
                "counter_view": row["counter_view"],
                "source_quote": row["source_quote"],
                "tweet_text": row["tweet_text"],
                "target_domain": target_domain,
                "chosen_style": row["chosen_style"] or "insider"
            }
            return item, analysis

    def log_feedback(self, article_id: str, action: str, tweet_text: str = "", notes: str = ""):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO editorial_feedback (article_id, action, tweet_text, notes)
                VALUES (?, ?, ?, ?)
            """, (article_id, action, tweet_text, notes))
            conn.commit()

    def get_feedback_stats(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT action, COUNT(*) as count FROM editorial_feedback GROUP BY action")
            return {row["action"]: row["count"] for row in cur.fetchall()}

