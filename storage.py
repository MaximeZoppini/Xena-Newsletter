import json
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
                conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
            except sqlite3.OperationalError:
                pass
            for col in ("chosen_style", "titre_fr", "chapo_fr", "statut", "confiance", "theme", "fiche_json"):
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
            # Articles déjà vus (ouverts, écoutés) : partagé entre tous les appareils
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen (
                    article_id TEXT PRIMARY KEY,
                    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Historique complet des conversations avec Xena
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL, -- 'user' ou 'model'
                    text TEXT NOT NULL,
                    article_id TEXT,
                    queries_json TEXT,
                    sources_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)
            # Dossiers vivants : une même histoire suivie dans le temps, une phrase par changement d'état
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dossiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    titre TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dossier_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    dossier_id INTEGER NOT NULL,
                    phrase TEXT NOT NULL,
                    statut TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
                )
            """)
            # role : 'evolution' (l'article fait avancer le dossier) ou 'corroboration' (autre source du même fait)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dossier_articles (
                    article_id TEXT PRIMARY KEY,
                    dossier_id INTEGER NOT NULL,
                    event_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    FOREIGN KEY (dossier_id) REFERENCES dossiers(id),
                    FOREIGN KEY (event_id) REFERENCES dossier_events(id)
                )
            """)
            # Synthèses 12 h : la phrase, les sections, les clusters notés et les corrections du contradicteur
            conn.execute("""
                CREATE TABLE IF NOT EXISTS syntheses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    debut TEXT,
                    phrase TEXT NOT NULL,
                    contenu_json TEXT NOT NULL,
                    clusters_json TEXT,
                    corrections_json TEXT,
                    contradicteur INTEGER DEFAULT 0,
                    model TEXT,
                    duree_s REAL
                )
            """)
            # Gap log : items ratés, fausses alertes, corrections du contradicteur, retours de Maxime
            conn.execute("""
                CREATE TABLE IF NOT EXISTS gap_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    origine TEXT NOT NULL, -- 'contradicteur' ou 'maxime'
                    type TEXT,
                    detail TEXT NOT NULL,
                    raison TEXT,
                    synthese_id INTEGER
                )
            """)
            # Notifications push : un abonnement par appareil, et le journal de ce qui a été envoyé (et pourquoi)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    endpoint TEXT PRIMARY KEY,
                    subscription_json TEXT NOT NULL,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    article_id TEXT,
                    dossier_id INTEGER,
                    event_id INTEGER,
                    titre TEXT,
                    corps TEXT,
                    raison TEXT,
                    envoyes INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_dossier_articles_d ON dossier_articles(dossier_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id)")
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
                    INSERT INTO articles (id, url, title, source, category, raw_summary, published_at, status, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    art_id,
                    article["url"],
                    article["title"],
                    article["source"],
                    article.get("category", "general"),
                    article.get("summary", ""),
                    article.get("published_at", ""),
                    "pending",
                    article.get("image", "")
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
                    factual_core, framing_detected, counter_view, source_quote, titre_fr, chapo_fr, statut, confiance, theme, fiche_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                analysis.get("statut", ""),
                analysis.get("confiance", ""),
                analysis.get("theme", ""),
                json.dumps(analysis["fiche"], ensure_ascii=False) if analysis.get("fiche") else None,
            ))
            conn.execute("UPDATE articles SET status = 'analyzed' WHERE id = ?", (article_id,))
            conn.commit()

    _LIST_COLUMNS = """
        a.id, a.url, a.title, a.source, a.category, a.raw_summary, a.published_at, a.ingested_at, a.image_url,
        an.global_score, an.systemic_impact, an.novelty_scoop, an.evidence_quality,
        an.factual_core, an.framing_detected, an.counter_view, an.source_quote,
        an.titre_fr, an.chapo_fr, an.statut, an.confiance, b.brief_json, (s.article_id IS NOT NULL) AS seen,
        da.dossier_id, da.role AS dossier_role, d.titre AS dossier_titre,
        (SELECT COUNT(*) FROM dossier_articles x WHERE x.dossier_id = da.dossier_id) AS dossier_n,
        (SELECT COUNT(*) FROM dossier_articles x LEFT JOIN seen sx ON sx.article_id = x.article_id
          WHERE x.dossier_id = da.dossier_id AND sx.article_id IS NULL) AS dossier_unseen,
        (SELECT e.phrase FROM dossier_events e WHERE e.dossier_id = da.dossier_id ORDER BY e.id DESC LIMIT 1) AS dossier_etat,
        (SELECT e.statut FROM dossier_events e WHERE e.dossier_id = da.dossier_id ORDER BY e.id DESC LIMIT 1) AS dossier_statut
    """
    _LIST_JOINS = """
        LEFT JOIN briefs b ON a.id = b.article_id
        LEFT JOIN seen s ON a.id = s.article_id
        LEFT JOIN dossier_articles da ON a.id = da.article_id
        LEFT JOIN dossiers d ON d.id = da.dossier_id
    """

    def list_articles(self, min_score: float = 0.0, limit: int = 40, offset: int = 0) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE an.global_score >= ?
                ORDER BY date(a.ingested_at, 'localtime') DESC, an.global_score DESC, a.ingested_at DESC
                LIMIT ? OFFSET ?
            """, (min_score, limit, offset)).fetchall()
            return [dict(r) for r in rows]

    def get_article(self, article_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}, b.source_text, an.theme, an.fiche_json, da.event_id
                FROM articles a
                LEFT JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE a.id = ?
            """, (article_id,)).fetchone()
            return dict(row) if row else None

    def list_recent(self, min_score: float, hours: int, unseen_only: bool = False, limit: int = 150,
                    skip_corroborations: bool = False) -> List[Dict[str, Any]]:
        """News importantes des dernières heures, de la plus ancienne à la plus récente."""
        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE an.global_score >= ?
                  AND datetime(a.ingested_at) >= datetime('now', ?)
                  {"AND s.article_id IS NULL" if unseen_only else ""}
                  {"AND COALESCE(da.role, '') != 'corroboration'" if skip_corroborations else ""}
                ORDER BY a.ingested_at DESC
                LIMIT ?
            """, (min_score, f"-{hours} hours", limit)).fetchall()
            return [dict(r) for r in reversed(rows)]

    def set_image(self, article_id: str, image_url: str):
        with self._get_connection() as conn:
            conn.execute("UPDATE articles SET image_url = ? WHERE id = ? AND COALESCE(image_url, '') = ''",
                         (image_url, article_id))
            conn.commit()

    def mark_seen(self, article_ids: List[str]):
        with self._get_connection() as conn:
            conn.executemany("INSERT OR IGNORE INTO seen (article_id) VALUES (?)", [(i,) for i in article_ids])
            conn.commit()

    def add_message(self, conversation_id: str, role: str, text: str, article_id: str = "",
                    queries: Optional[List[str]] = None, sources: Optional[List[Dict[str, str]]] = None):
        import json
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO conversations (id) VALUES (?)
                ON CONFLICT(id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """, (conversation_id,))
            conn.execute("""
                INSERT INTO messages (conversation_id, role, text, article_id, queries_json, sources_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (conversation_id, role, text, article_id or None,
                  json.dumps(queries or [], ensure_ascii=False), json.dumps(sources or [], ensure_ascii=False)))
            conn.commit()

    def get_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        import json
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT role, text, article_id, queries_json, sources_json, created_at
                FROM messages WHERE conversation_id = ? ORDER BY id
            """, (conversation_id,)).fetchall()
        return [{
            "role": r["role"], "text": r["text"], "article_id": r["article_id"], "created_at": r["created_at"],
            "queries": json.loads(r["queries_json"] or "[]"), "sources": json.loads(r["sources_json"] or "[]"),
        } for r in rows]

    # ------------------------------------------------------------- dossiers
    def open_dossiers(self, days: int = 7, limit: int = 60) -> List[Dict[str, Any]]:
        """Dossiers ouverts (un dossier qui n'a pas bougé depuis `days` jours est fermé), avec leur état actuel."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT d.id, d.titre, d.updated_at,
                       (SELECT e.phrase FROM dossier_events e WHERE e.dossier_id = d.id ORDER BY e.id DESC LIMIT 1) AS etat
                FROM dossiers d
                WHERE datetime(d.updated_at) >= datetime('now', ?)
                ORDER BY d.updated_at DESC
                LIMIT ?
            """, (f"-{days} days", limit)).fetchall()
            return [dict(r) for r in rows]

    def attach_to_dossier(self, article_id: str, dossier_id: Optional[int], titre: str,
                          phrase: str, statut: str, evolution: bool) -> int:
        """Range un article dans un dossier (créé au besoin). Retourne l'id du dossier."""
        with self._get_connection() as conn:
            if dossier_id is None:
                dossier_id = conn.execute("INSERT INTO dossiers (titre) VALUES (?)", (titre,)).lastrowid
                evolution = True
            last = conn.execute("SELECT id FROM dossier_events WHERE dossier_id = ? ORDER BY id DESC LIMIT 1",
                                (dossier_id,)).fetchone()
            if evolution or not last:
                event_id = conn.execute("INSERT INTO dossier_events (dossier_id, phrase, statut) VALUES (?, ?, ?)",
                                        (dossier_id, phrase, statut)).lastrowid
                role = "evolution"
            else:
                event_id, role = last["id"], "corroboration"
            conn.execute("INSERT OR REPLACE INTO dossier_articles (article_id, dossier_id, event_id, role) VALUES (?, ?, ?, ?)",
                         (article_id, dossier_id, event_id, role))
            conn.execute("UPDATE dossiers SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (dossier_id,))
            conn.commit()
            return dossier_id

    def is_in_dossier(self, article_id: str) -> bool:
        with self._get_connection() as conn:
            return conn.execute("SELECT 1 FROM dossier_articles WHERE article_id = ?", (article_id,)).fetchone() is not None

    def get_dossier(self, dossier_id: int) -> Optional[Dict[str, Any]]:
        """Le dossier et son fil, du plus récent au plus ancien, avec les articles de chaque étape."""
        with self._get_connection() as conn:
            d = conn.execute("SELECT id, titre, created_at, updated_at FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
            if not d:
                return None
            events = [dict(e) for e in conn.execute(
                "SELECT id, phrase, statut, created_at FROM dossier_events WHERE dossier_id = ? ORDER BY id DESC",
                (dossier_id,)).fetchall()]
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}, da.event_id
                FROM articles a
                LEFT JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE da.dossier_id = ?
                ORDER BY a.ingested_at
            """, (dossier_id,)).fetchall()
        by_event: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            by_event.setdefault(r["event_id"], []).append(dict(r))
        for e in events:
            e["articles"] = by_event.get(e["id"], [])
        return {**dict(d), "events": events}

    def dossier_events_since(self, since: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT e.dossier_id, d.titre, e.phrase, e.statut, e.created_at,
                       (SELECT COUNT(*) FROM dossier_articles x WHERE x.event_id = e.id) AS sources
                FROM dossier_events e JOIN dossiers d ON d.id = e.dossier_id
                WHERE datetime(e.created_at) > datetime(?)
                ORDER BY e.dossier_id, e.id
            """, (since,)).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------- synthèses
    def articles_since(self, since: str, min_score: float) -> List[Dict[str, Any]]:
        """Items analysés depuis `since` (UTC, format SQLite), hors thème « autre », avec leur fiche."""
        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}, an.theme, an.fiche_json
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE datetime(a.ingested_at) > datetime(?)
                  AND an.global_score >= ?
                  AND COALESCE(an.theme, '') != 'autre'
                ORDER BY a.ingested_at
            """, (since, min_score)).fetchall()
            return [dict(r) for r in rows]

    def save_synthese(self, data: Dict[str, Any]) -> int:
        with self._get_connection() as conn:
            sid = conn.execute("""
                INSERT INTO syntheses (debut, phrase, contenu_json, clusters_json, corrections_json, contradicteur, model, duree_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (data["debut"], data["phrase"], json.dumps(data["contenu"], ensure_ascii=False),
                  json.dumps(data["clusters"], ensure_ascii=False), json.dumps(data["corrections"], ensure_ascii=False),
                  1 if data["contradicteur"] else 0, data["model"], data["duree_s"])).lastrowid
            conn.commit()
            return sid

    def _synthese_row(self, r) -> Dict[str, Any]:
        return {
            "id": r["id"], "created_at": r["created_at"], "debut": r["debut"], "phrase": r["phrase"],
            "contenu": json.loads(r["contenu_json"]),
            "clusters": json.loads(r["clusters_json"] or "[]"),
            "corrections": json.loads(r["corrections_json"] or "[]"),
            "contradicteur": bool(r["contradicteur"]), "model": r["model"], "duree_s": r["duree_s"],
        }

    def last_syntheses(self, n: int = 3) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM syntheses ORDER BY id DESC LIMIT ?", (n,)).fetchall()
            return [self._synthese_row(r) for r in rows]

    def get_synthese(self, synthese_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Une synthèse (la dernière par défaut), avec les ids de la précédente et de la suivante."""
        with self._get_connection() as conn:
            if synthese_id is None:
                r = conn.execute("SELECT * FROM syntheses ORDER BY id DESC LIMIT 1").fetchone()
            else:
                r = conn.execute("SELECT * FROM syntheses WHERE id = ?", (synthese_id,)).fetchone()
            if not r:
                return None
            prev = conn.execute("SELECT MAX(id) FROM syntheses WHERE id < ?", (r["id"],)).fetchone()[0]
            nxt = conn.execute("SELECT MIN(id) FROM syntheses WHERE id > ?", (r["id"],)).fetchone()[0]
        return {**self._synthese_row(r), "prev_id": prev, "next_id": nxt}

    def log_gap(self, origine: str, detail: str, type_: str = "", raison: str = "", synthese_id: Optional[int] = None):
        with self._get_connection() as conn:
            conn.execute("INSERT INTO gap_log (origine, type, detail, raison, synthese_id) VALUES (?, ?, ?, ?, ?)",
                         (origine, type_, detail, raison, synthese_id))
            conn.commit()

    def recent_gaps(self, days: int = 7, limit: int = 60) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT created_at, origine, type, detail, raison FROM gap_log
                WHERE datetime(created_at) >= datetime('now', ?)
                ORDER BY id DESC LIMIT ?
            """, (f"-{days} days", limit)).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------- notifications push
    def event_articles(self, article_id: str) -> List[Dict[str, Any]]:
        """Les articles qui racontent le même fait (même étape de dossier) ; à défaut, l'article seul."""
        with self._get_connection() as conn:
            rows = conn.execute(f"""
                SELECT {self._LIST_COLUMNS}, an.theme, an.fiche_json, da.event_id
                FROM articles a
                JOIN analyses an ON a.id = an.article_id
                {self._LIST_JOINS}
                WHERE a.id = ? OR da.event_id = (SELECT event_id FROM dossier_articles WHERE article_id = ?)
                ORDER BY an.global_score DESC
            """, (article_id, article_id)).fetchall()
            return [dict(r) for r in rows]

    def save_subscription(self, endpoint: str, subscription_json: str, user_agent: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO push_subscriptions (endpoint, subscription_json, user_agent) VALUES (?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET subscription_json = excluded.subscription_json
            """, (endpoint, subscription_json, user_agent))
            conn.commit()

    def delete_subscription(self, endpoint: str):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
            conn.commit()

    def list_subscriptions(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT endpoint, subscription_json FROM push_subscriptions").fetchall()]

    def has_subscription(self, endpoint: str) -> bool:
        with self._get_connection() as conn:
            return conn.execute("SELECT 1 FROM push_subscriptions WHERE endpoint = ?", (endpoint,)).fetchone() is not None

    def already_pushed(self, article_ids: List[str], event_id: Optional[int], dossier_id: Optional[int], hours: int) -> bool:
        """Déjà notifié : un de ces articles, cette étape de dossier, ou ce dossier dans les `hours` dernières heures."""
        with self._get_connection() as conn:
            marks = ",".join("?" * len(article_ids)) or "''"
            row = conn.execute(f"""
                SELECT 1 FROM push_log
                WHERE article_id IN ({marks})
                   OR (? IS NOT NULL AND event_id = ?)
                   OR (? IS NOT NULL AND dossier_id = ? AND datetime(created_at) >= datetime('now', ?))
                LIMIT 1
            """, (*article_ids, event_id, event_id, dossier_id, dossier_id, f"-{hours} hours")).fetchone()
            return row is not None

    def log_push(self, data: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO push_log (article_id, dossier_id, event_id, titre, corps, raison, envoyes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data.get("article_id"), data.get("dossier_id"), data.get("event_id"), data.get("titre"),
                  data.get("corps"), data.get("raison"), data.get("envoyes", 0)))
            conn.commit()

    def recent_pushes(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT created_at, article_id, titre, corps, raison, envoyes FROM push_log ORDER BY id DESC LIMIT ?",
                                (limit,)).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------- état
    def get_state(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None

    def set_state(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO app_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            conn.commit()

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
