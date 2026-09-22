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
            # Table de télémétrie hybride (suivi en direct des coûts, temps et réponses Jev vs Gemini)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hybrid_eval_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    url TEXT,
                    jev_latency_ms INTEGER DEFAULT 0,
                    jev_p_scoop REAL DEFAULT 0.0,
                    jev_p_opinion REAL DEFAULT 0.0,
                    jev_systemic_score REAL DEFAULT 0.0,
                    jev_decision TEXT NOT NULL, -- 'QUALIFIED' ou 'REJECTED'
                    jev_reason TEXT,
                    jev_tokens_in INTEGER DEFAULT 0,
                    jev_tokens_out INTEGER DEFAULT 0,
                    gemini_called INTEGER DEFAULT 0,
                    gemini_latency_ms INTEGER DEFAULT 0,
                    gemini_tokens_in INTEGER DEFAULT 0,
                    gemini_tokens_out INTEGER DEFAULT 0,
                    gemini_score REAL DEFAULT 0.0,
                    gemini_tweet TEXT DEFAULT '',
                    cost_without_jev REAL DEFAULT 0.0,
                    cost_hybrid REAL DEFAULT 0.0,
                    savings REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

    def log_hybrid_eval(self, data: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO hybrid_eval_logs (
                    article_id, title, source, url,
                    jev_latency_ms, jev_p_scoop, jev_p_opinion, jev_systemic_score,
                    jev_decision, jev_reason, jev_tokens_in, jev_tokens_out,
                    gemini_called, gemini_latency_ms, gemini_tokens_in, gemini_tokens_out,
                    gemini_score, gemini_tweet, cost_without_jev, cost_hybrid, savings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("article_id", ""),
                data.get("title", ""),
                data.get("source", ""),
                data.get("url", ""),
                data.get("jev_latency_ms", 0),
                data.get("jev_p_scoop", 0.0),
                data.get("jev_p_opinion", 0.0),
                data.get("jev_systemic_score", 0.0),
                data.get("jev_decision", "REJECTED"),
                data.get("jev_reason", ""),
                data.get("jev_tokens_in", 0),
                data.get("jev_tokens_out", 0),
                1 if data.get("gemini_called") else 0,
                data.get("gemini_latency_ms", 0),
                data.get("gemini_tokens_in", 0),
                data.get("gemini_tokens_out", 0),
                data.get("gemini_score", 0.0),
                data.get("gemini_tweet", ""),
                data.get("cost_without_jev", 0.0),
                data.get("cost_hybrid", 0.0),
                data.get("savings", 0.0)
            ))
            conn.commit()

    def get_hybrid_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_count,
                    SUM(CASE WHEN jev_decision = 'REJECTED' THEN 1 ELSE 0 END) as rejected_count,
                    SUM(CASE WHEN jev_decision = 'QUALIFIED' THEN 1 ELSE 0 END) as qualified_count,
                    AVG(jev_latency_ms) as avg_jev_latency,
                    AVG(CASE WHEN gemini_called = 1 THEN gemini_latency_ms ELSE NULL END) as avg_gemini_latency,
                    SUM(cost_without_jev) as total_cost_without_jev,
                    SUM(cost_hybrid) as total_cost_hybrid,
                    SUM(savings) as total_savings
                FROM hybrid_eval_logs
            """)
            row = cur.fetchone()
            if not row or not row["total_count"]:
                return {
                    "total_count": 0,
                    "rejected_count": 0,
                    "qualified_count": 0,
                    "filter_rate_pct": 0.0,
                    "avg_jev_latency_ms": 0,
                    "avg_gemini_latency_ms": 0,
                    "speedup_factor": 1.0,
                    "total_cost_without_jev": 0.0,
                    "total_cost_hybrid": 0.0,
                    "total_savings": 0.0,
                    "savings_pct": 0.0
                }

            total = row["total_count"]
            rej = row["rejected_count"] or 0
            qual = row["qualified_count"] or 0
            filter_rate = round((rej / total) * 100, 1) if total > 0 else 0.0
            avg_jev = round(row["avg_jev_latency"] or 0)
            avg_gemini = round(row["avg_gemini_latency"] or 0)
            speedup = round(avg_gemini / avg_jev, 1) if avg_jev > 0 and avg_gemini > 0 else 1.0

            c_without = round(row["total_cost_without_jev"] or 0.0, 5)
            c_hybrid = round(row["total_cost_hybrid"] or 0.0, 5)
            savings = round(row["total_savings"] or 0.0, 5)
            savings_pct = round((savings / c_without) * 100, 1) if c_without > 0 else 0.0

            return {
                "total_count": total,
                "rejected_count": rej,
                "qualified_count": qual,
                "filter_rate_pct": filter_rate,
                "avg_jev_latency_ms": avg_jev,
                "avg_gemini_latency_ms": avg_gemini,
                "speedup_factor": speedup,
                "total_cost_without_jev": c_without,
                "total_cost_hybrid": c_hybrid,
                "total_savings": savings,
                "savings_pct": savings_pct
            }

    def get_hybrid_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM hybrid_eval_logs ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cur.fetchall()]


