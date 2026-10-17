"""
Serveur web du site de lecture : sert l'interface (static/) et une petite API JSON.
Il écoute en local uniquement ; le tailnet y accède en HTTPS via `tailscale serve`.
"""
import base64
import json
import logging
import mimetypes
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from briefing import Briefer
from config import MIN_INTEREST_SCORE, STATIC_DIR
from storage import Storage

logger = logging.getLogger("web")

MAX_BODY = 25 * 1024 * 1024  # ~10 min d'audio WAV 16 kHz
ARTICLE_RE = re.compile(r"^/api/articles/([0-9a-f]{16})(/audio)?$")
CONV_RE = re.compile(r"^/api/conversations/([0-9a-zA-Z-]{8,64})$")
AUDIO_TYPES = {"audio/mp4", "audio/aac", "audio/webm", "audio/ogg", "audio/wav", "audio/mpeg"}


def _article_card(row: dict) -> dict:
    brief = json.loads(row["brief_json"]) if row.get("brief_json") else {}
    return {
        "id": row["id"],
        "url": row["url"],
        "source": row["source"],
        "category": row["category"],
        "published_at": row["published_at"],
        "ingested_at": row["ingested_at"],
        "score": row["global_score"],
        "image": row.get("image_url") or "",
        "scores": {
            "impact": row["systemic_impact"],
            "nouveaute": row["novelty_scoop"],
            "preuves": row["evidence_quality"],
        },
        "title_original": row["title"],
        "titre": brief.get("titre") or row.get("titre_fr") or row["title"],
        "chapo": brief.get("chapo") or row.get("chapo_fr") or row.get("factual_core") or row.get("raw_summary") or "",
        "has_brief": bool(brief),
        "seen": bool(row.get("seen")),
    }


class Handler(BaseHTTPRequestHandler):
    storage: Storage = None
    briefer: Briefer = None

    def log_message(self, fmt, *args):
        logger.debug(fmt % args)

    # ---------------------------------------------------------------- helpers
    def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Corps de requête invalide")
        return json.loads(self.rfile.read(length))

    def _static(self, rel: str):
        root = Path(STATIC_DIR).resolve()
        path = (root / rel).resolve()
        if root not in path.parents or not path.is_file():
            return self._json(404, {"error": "introuvable"})
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, path.read_bytes(), ctype, cache="no-cache")

    # ----------------------------------------------------------------- routes
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                return self._static("index.html")
            if url.path.startswith("/static/"):
                return self._static(url.path[len("/static/"):])
            if url.path == "/api/articles":
                q = parse_qs(url.query)
                min_score = MIN_INTEREST_SCORE if q.get("filtre", ["top"])[0] == "top" else 0.0
                limit = min(int(q.get("limit", ["40"])[0]), 100)
                offset = max(int(q.get("offset", ["0"])[0]), 0)
                rows = self.storage.list_articles(min_score=min_score, limit=limit, offset=offset)
                return self._json(200, {"articles": [_article_card(r) for r in rows], "seuil": MIN_INTEREST_SCORE})
            m = ARTICLE_RE.match(url.path)
            if m and not m.group(2):
                row = self.storage.get_article(m.group(1))
                if not row:
                    return self._json(404, {"error": "article introuvable"})
                brief = self.briefer.get_or_create_brief(row["id"])
                row = self.storage.get_article(row["id"])
                card = _article_card(row) if row.get("global_score") is not None else {"id": row["id"]}
                return self._json(200, {
                    **card,
                    "brief": brief,
                    "factual_core": row.get("factual_core"),
                    "counter_view": row.get("counter_view"),
                    "framing": row.get("framing_detected"),
                    "source_quote": row.get("source_quote"),
                })
            c = CONV_RE.match(url.path)
            if c:
                return self._json(200, {"messages": self.storage.get_messages(c.group(1))})
            if url.path == "/api/flash":
                rows = self.storage.list_recent(min_score=MIN_INTEREST_SCORE, hours=72, unseen_only=True, limit=20)
                return self._json(200, {"articles": [_article_card(r) for r in rows]})
            if m and m.group(2):
                court = parse_qs(url.query).get("version", [""])[0] == "court"
                get_audio = self.briefer.get_or_create_short_audio if court else self.briefer.get_or_create_summary_audio
                audio = get_audio(m.group(1))
                if not audio:
                    return self._json(502, {"error": "génération audio impossible"})
                return self._send(200, audio, "audio/wav", cache="private, max-age=86400")
            return self._json(404, {"error": "introuvable"})
        except Exception as e:
            logger.error(f"GET {url.path} : {e}", exc_info=True)
            return self._json(500, {"error": str(e)})

    def do_POST(self):
        url = urlparse(self.path)
        try:
            body = self._read_json()
            if url.path == "/api/tts":
                text = (body.get("text") or "").strip()[:4000]
                audio = self.briefer.synthesize(text)
                if not audio:
                    return self._json(502, {"error": "synthèse vocale impossible"})
                return self._send(200, audio, "audio/wav")
            if url.path == "/api/seen":
                ids = [i for i in body.get("ids", []) if isinstance(i, str) and re.fullmatch(r"[0-9a-f]{16}", i)]
                self.storage.mark_seen(ids)
                return self._json(200, {"ok": True})
            if url.path == "/api/transcribe":
                mime = (body.get("mime") or "").split(";")[0].strip()
                if mime not in AUDIO_TYPES or not body.get("audio_b64"):
                    return self._json(400, {"error": f"format audio non pris en charge ({mime})"})
                audio = base64.b64decode(body["audio_b64"])
                logger.info(f"🎙 Question vocale reçue : {len(audio) // 1024} Ko ({mime})")
                return self._json(200, {"text": self.briefer.transcribe(audio, mime)})
            if url.path == "/api/chat":
                article_id = body.get("article_id") or ""
                conversation_id = body.get("conversation_id") or ""
                if article_id and (not re.fullmatch(r"[0-9a-f]{16}", article_id) or not self.storage.get_article(article_id)):
                    return self._json(404, {"error": "article introuvable"})
                if not re.fullmatch(r"[0-9a-zA-Z-]{8,64}", conversation_id):
                    return self._json(400, {"error": "conversation invalide"})
                text = (body.get("text") or "").strip()
                if not text:
                    return self._json(400, {"error": "question vide"})
                return self._json(200, self.briefer.chat(conversation_id, article_id, text))
            return self._json(404, {"error": "introuvable"})
        except (BrokenPipeError, ConnectionResetError):
            logger.info(f"POST {url.path} : le navigateur a fermé la connexion avant la réponse")
        except Exception as e:
            logger.error(f"POST {url.path} : {e}", exc_info=True)
            try:
                return self._json(500, {"error": str(e)})
            except (BrokenPipeError, ConnectionResetError):
                pass


def start_web_server(storage: Storage, briefer: Briefer, host: str, port: int) -> ThreadingHTTPServer:
    Handler.storage = storage
    Handler.briefer = briefer
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True, name="web").start()
    logger.info(f"🌐 Site disponible sur http://{host}:{port}")
    return server
