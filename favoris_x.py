"""Favoris X de Maxime : récupère les nouveaux favoris dans data/favoris_x.md.

  python favoris_x.py auth           -> affiche le lien d'autorisation
  python favoris_x.py code <URL>     -> enregistre les jetons (URL de retour 127.0.0.1)
  python favoris_x.py                -> ajoute les nouveaux favoris

Jetons et favoris vus dans data/ (hors git, droits 600). Coût : 0,001 $ par favori lu.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CLIENT_ID = os.getenv("X_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("X_REDIRECT_URI", "http://127.0.0.1:8765/callback")
SCOPES = "bookmark.read tweet.read users.read offline.access"
API = "https://api.x.com/2"

DATA_DIR = BASE_DIR / "data"
AUTH_FILE = DATA_DIR / "x_auth.json"
VUS_FILE = DATA_DIR / "favoris_x_vus.json"
SORTIE = DATA_DIR / "favoris_x.md"

# Premier passage : on ne remonte que les plus récents, pour ne pas vider les crédits
PREMIER_PASSAGE_MAX = int(os.getenv("X_FAVORIS_PREMIER_MAX", "100"))
# Passages suivants : chaque favori relu est facturé, donc on sonde 1 favori,
# puis les 5 suivants s'il est nouveau, puis par pages de 100
PAGES_SONDAGE = [1, 5]


def _lire(path, defaut):
    return json.loads(path.read_text()) if path.exists() else defaut


def _ecrire(path, data):
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.chmod(path, 0o600)


def _token_post(data):
    r = requests.post(f"{API}/oauth2/token", data=data, auth=(CLIENT_ID, CLIENT_SECRET), timeout=30)
    r.raise_for_status()
    t = r.json()
    t["expires_at"] = time.time() + t.get("expires_in", 7200) - 60
    return t


def auth():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _ecrire(AUTH_FILE, {**_lire(AUTH_FILE, {}), "pkce": {"verifier": verifier, "state": state}})
    print("https://x.com/i/oauth2/authorize?" + urlencode({
        "response_type": "code", "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI,
        "scope": SCOPES, "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    }))


def code(url_retour):
    auth_data = _lire(AUTH_FILE, {})
    pkce = auth_data.get("pkce") or sys.exit("Lancer d'abord : favoris_x.py auth")
    q = parse_qs(urlparse(url_retour).query)
    if q.get("state", [""])[0] != pkce["state"]:
        sys.exit("State invalide : relancer favoris_x.py auth")
    t = _token_post({"grant_type": "authorization_code", "code": q["code"][0],
                     "redirect_uri": REDIRECT_URI, "code_verifier": pkce["verifier"]})
    me = requests.get(f"{API}/users/me", headers={"Authorization": f"Bearer {t['access_token']}"}, timeout=30)
    me.raise_for_status()
    t["user_id"] = me.json()["data"]["id"]
    _ecrire(AUTH_FILE, t)
    print(f"OK, connecté en tant que @{me.json()['data']['username']}")


def _jeton():
    t = _lire(AUTH_FILE, {})
    if "access_token" not in t:
        sys.exit("Pas de jeton : favoris_x.py auth puis code")
    if time.time() > t["expires_at"]:
        neuf = _token_post({"grant_type": "refresh_token", "refresh_token": t["refresh_token"]})
        t = {**neuf, "user_id": t["user_id"]}
        _ecrire(AUTH_FILE, t)
    return t


def _video(media):
    mp4 = [v for v in media.get("variants", []) if v.get("content_type") == "video/mp4"]
    return max(mp4, key=lambda v: v.get("bit_rate", 0))["url"] if mp4 else None


def _formater(tweet, users, medias):
    auteur = users.get(tweet["author_id"], {})
    texte = (tweet.get("note_tweet") or {}).get("text") or tweet["text"]
    for u in (tweet.get("entities") or {}).get("urls", []):
        texte = texte.replace(u["url"], u.get("expanded_url", u["url"]))
    lignes = [
        f"## @{auteur.get('username', '?')} ({auteur.get('name', '')}) — {tweet.get('created_at', '')[:10]}",
        f"https://x.com/{auteur.get('username', 'i')}/status/{tweet['id']}",
        "", texte, "",
    ]
    for k in (tweet.get("attachments") or {}).get("media_keys", []):
        m = medias.get(k, {})
        if m.get("type") in ("video", "animated_gif"):
            lignes.append(f"- Vidéo : {_video(m) or m.get('preview_image_url', '')}")
    return "\n".join(lignes).rstrip() + "\n"


def recuperer():
    t = _jeton()
    vus = set(_lire(VUS_FILE, []))
    premier = not vus
    nouveaux, page, n_page = [], None, 0
    while True:
        params = {
            "max_results": 100 if premier or n_page >= len(PAGES_SONDAGE) else PAGES_SONDAGE[n_page],
            "tweet.fields": "created_at,entities,note_tweet,attachments,author_id",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "username,name",
            "media.fields": "type,variants,preview_image_url",
        }
        if page:
            params["pagination_token"] = page
        r = requests.get(f"{API}/users/{t['user_id']}/bookmarks", params=params,
                         headers={"Authorization": f"Bearer {t['access_token']}"}, timeout=30)
        r.raise_for_status()
        corps = r.json()
        users = {u["id"]: u for u in corps.get("includes", {}).get("users", [])}
        medias = {m["media_key"]: m for m in corps.get("includes", {}).get("media", [])}
        deja_vu = False
        for tweet in corps.get("data", []):
            if tweet["id"] in vus:
                deja_vu = True
                break
            nouveaux.append(_formater(tweet, users, medias))
            vus.add(tweet["id"])
        page = corps.get("meta", {}).get("next_token")
        n_page += 1
        if deja_vu or not page or (premier and len(nouveaux) >= PREMIER_PASSAGE_MAX):
            break

    if nouveaux:
        DATA_DIR.mkdir(exist_ok=True)
        entete = f"\n# Récupérés le {datetime.now():%d/%m/%Y %H:%M}\n\n"
        with SORTIE.open("a") as f:
            f.write(entete + "\n".join(nouveaux))
    _ecrire(VUS_FILE, sorted(vus))
    print(f"{len(nouveaux)} nouveau(x) favori(s)")


if __name__ == "__main__":
    if sys.argv[1:2] == ["auth"]:
        auth()
    elif sys.argv[1:2] == ["code"] and len(sys.argv) > 2:
        code(sys.argv[2])
    else:
        recuperer()
