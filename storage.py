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
            for col in ("chosen_style", "titre_fr", "chapo_fr"):
                try:
                    conn.execute(f"ALTER TABLE analyses ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass
            # Fiches de lecture complètes (texte de l'article récupéré + brief en français)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS briefs (
                    article_id TEXT PRIMARY KEY,
                    brief_json TEXT NOT NULL,
                    source_text TEXT,
                    model TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_ingested ON articles(ingested_at)")
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
                    factual_core, framing_detected, counter_view, source_quote, titre_fr, chapo_fr
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                analysis.get("titre_fr", ""),
                analysis.get("chapo_fr", ""),
            ))
            conn.execute("UPDATE articles SET status = 'analyzed' WHERE id = ?", (article_id,))
            conn.commit()

    _LIST_COLUMNS = """
        a.id, a.url, a.title, a.source, a.category, a.raw_summary, a.published_at, a.ingested_at,
        an.global_score, an.systemic_impact, an.novelty_scoop, an.evidence_quality,
        an.factual_core, an.framing_detected, an.counter_view, an.source_quote,
        an.titre_fr, an.chapo_fr, b.brief_json
    """

    def list_articles(self, min_score: float = 0.0, limit: int = 40, offset: int = 0) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                LEFT JOIN briefs b ON a.id = b.article_id
                WHERE an.global_score >= ?
                ORDER BY a.ingested_at DESC
                LIMIT ? OFFSET ?
            """, (min_score, limit, offset)).fetchall()
            return [dict(r) for r in rows]

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}, b.source_text
                FROM articles a
                LEFT JOIN analyses an ON a.id = an.article_id
                LEFT JOIN briefs b ON a.id = b.article_id
                WHERE a.id = ?
            """, (article_id,)).fetchone()
            return dict(row) if row else None

    def save_brief(self, article_id: str, brief_json: str, source_text: str, model: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO briefs (article_id, brief_json, source_text, model)
                VALUES (?, ?, ?, ?)
            """, (article_id, brief_json, source_text, model))
            conn.commit()

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
