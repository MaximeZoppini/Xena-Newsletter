"""
La to-do de Maxime : un seul fichier, data/todo.json (hors git, rien n'est effacé aux mises à jour).

Deux écrivains passent par ce module, jamais à la main :
- le site Xena (Maxime coche, ajoute, supprime) ;
- l'agent Agenda, par SSH, via la commande bin/xena-todo.
Chaque lecture prend un verrou partagé, chaque écriture un verrou exclusif (flock sur todo.json.lock) :
une modification d'Agenda et un clic sur le site ne s'écrasent jamais.

Uniquement la bibliothèque standard : la commande tourne sous l'utilisateur « agenda », qui n'a pas accès à .env.

Format :
{"version": 1, "taches": [{
    "id": "3f9c1a2b7d4e",          12 caractères hexadécimaux, attribué à la création
    "texte": "Appeler le notaire",
    "echeance": "2026-10-26",       AAAA-MM-JJ ou null
    "heure": "10:30",               HH:MM ou null
    "groupe": "Administratif",      libre ou null
    "projet": "Infra",              libre ou null : le site classe les tâches par projet
    "urgence": "semaine",           "aujourd'hui", "semaine", "un jour" ou null
    "source": "agenda",             qui l'a créée : "agenda" ou "maxime"
    "fait": false,
    "fait_par": null,               "agenda" ou "maxime" quand elle est faite
    "fait_le": null,                horodatage ISO quand elle est faite
    "cree_le": "2026-10-23T14:05:00+02:00",
    "modifie_le": "2026-10-23T14:05:00+02:00"
}]}
"""
import fcntl
import grp
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
TODO_PATH = Path(os.getenv("XENA_TODO_PATH", str(BASE_DIR / "data" / "todo.json")))
LOCK_PATH = TODO_PATH.with_name(TODO_PATH.name + ".lock")
BACKUP_PATH = TODO_PATH.with_name("todo.backup.json")
GROUPE_UNIX = "agenda"  # groupe propriétaire des fichiers : l'agent Agenda y écrit sans droit sur le reste de data/

AUTEURS = ("agenda", "maxime")
DATE_RE = re.compile(r"^20\d\d-[01]\d-[0-3]\d$")
HEURE_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_TEXTE = 300
URGENCES = ("aujourd'hui", "semaine", "un jour")


class TodoError(Exception):
    """Erreur d'usage : tâche introuvable, date invalide, fichier illisible…"""


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _prepare(path: Path):
    """Crée le fichier s'il manque, lisible et modifiable par root et le groupe « agenda » seulement."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o660))
    try:
        gid = grp.getgrnam(GROUPE_UNIX).gr_gid
        st = path.stat()
        if st.st_gid != gid or (st.st_mode & 0o777) != 0o660:
            os.chown(path, -1, gid)
            os.chmod(path, 0o660)
    except (KeyError, PermissionError):
        pass  # groupe absent (poste de dev) ou pas root : on garde les droits par défaut


def initialiser():
    """Appelé par le service Xena (root) : crée les fichiers avec les bons droits, même si le groupe
    « agenda » apparaît après coup, et tient la copie de secours à jour."""
    _prepare(TODO_PATH)
    _prepare(LOCK_PATH)
    lister(backup=True)


@contextmanager
def _locked(exclusive: bool):
    _prepare(LOCK_PATH)
    with open(LOCK_PATH, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _read() -> Dict[str, Any]:
    if not TODO_PATH.exists() or TODO_PATH.stat().st_size == 0:
        return {"version": 1, "taches": []}
    try:
        data = json.loads(TODO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise TodoError(f"{TODO_PATH} illisible ({e}) ; dernière version saine : {BACKUP_PATH}")
    if not isinstance(data, dict) or not isinstance(data.get("taches"), list):
        raise TodoError(f"{TODO_PATH} n'a pas le format attendu")
    return data


def _write(data: Dict[str, Any]):
    """Écriture sur place (Agenda n'a pas le droit de créer des fichiers dans data/), sous verrou exclusif."""
    _prepare(TODO_PATH)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with open(TODO_PATH, "r+", encoding="utf-8") as f:
        f.seek(0)
        f.write(text)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())


def _backup(data: Dict[str, Any]):
    """Copie de secours tenue par le service Xena (root), au cas où le fichier serait abîmé."""
    try:
        BACKUP_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except PermissionError:
        pass  # l'utilisateur agenda ne peut pas : c'est le service qui s'en charge


def _check_date(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    if not DATE_RE.match(value):
        raise TodoError(f"échéance invalide « {value} » : AAAA-MM-JJ attendu")
    return value


def _check_heure(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    m = re.fullmatch(r"(\d{1,2})[:h](\d{2})", value)
    value = f"{int(m.group(1)):02d}:{m.group(2)}" if m else value
    if not HEURE_RE.match(value):
        raise TodoError(f"heure invalide « {value} » : HH:MM attendu")
    return value


def _check_urgence(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    norm = " ".join(value.strip().lower().replace("’", "'").replace("-", " ").split())
    norm = {"aujourdhui": "aujourd'hui", "unjour": "un jour"}.get(norm.replace(" ", "").replace("'", ""), norm)
    if norm not in URGENCES:
        raise TodoError(f"urgence invalide « {value} » : aujourd'hui, semaine ou un jour")
    return norm


def _court(value: Optional[str]) -> Optional[str]:
    return (value or "").strip()[:80] or None


def _check_texte(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise TodoError("texte vide")
    return value[:MAX_TEXTE]


def _find(data: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    for t in data["taches"]:
        if t.get("id") == task_id:
            return t
    raise TodoError(f"tâche introuvable : {task_id}")


# ------------------------------------------------------------------ API
def lister(backup: bool = False) -> List[Dict[str, Any]]:
    with _locked(exclusive=False):
        data = _read()
    if backup:
        _backup(data)
    return data["taches"]


def ajouter(texte: str, par: str, echeance: Optional[str] = None, heure: Optional[str] = None,
            groupe: Optional[str] = None, projet: Optional[str] = None, urgence: Optional[str] = None) -> Dict[str, Any]:
    if par not in AUTEURS:
        raise TodoError(f"auteur inconnu : {par}")
    now = _now()
    tache = {
        "id": uuid.uuid4().hex[:12], "texte": _check_texte(texte),
        "echeance": _check_date(echeance), "heure": _check_heure(heure),
        "groupe": _court(groupe), "projet": _court(projet), "urgence": _check_urgence(urgence), "source": par,
        "fait": False, "fait_par": None, "fait_le": None, "cree_le": now, "modifie_le": now,
    }
    with _locked(exclusive=True):
        data = _read()
        data["taches"].append(tache)
        _write(data)
    return tache


def cocher(task_id: str, par: str, fait: bool = True) -> Dict[str, Any]:
    if par not in AUTEURS:
        raise TodoError(f"auteur inconnu : {par}")
    with _locked(exclusive=True):
        data = _read()
        t = _find(data, task_id)
        if bool(t.get("fait")) != fait:
            t.update({"fait": fait, "fait_par": par if fait else None, "fait_le": _now() if fait else None,
                      "modifie_le": _now()})
            _write(data)
    return t


def modifier(task_id: str, texte: Optional[str] = None, echeance: Optional[str] = None,
             heure: Optional[str] = None, groupe: Optional[str] = None, projet: Optional[str] = None,
             urgence: Optional[str] = None) -> Dict[str, Any]:
    """None = inchangé ; chaîne vide = effacer (échéance, heure, groupe, projet, urgence)."""
    with _locked(exclusive=True):
        data = _read()
        t = _find(data, task_id)
        if texte is not None:
            t["texte"] = _check_texte(texte)
        if echeance is not None:
            t["echeance"] = _check_date(echeance)
        if heure is not None:
            t["heure"] = _check_heure(heure)
        if groupe is not None:
            t["groupe"] = _court(groupe)
        if projet is not None:
            t["projet"] = _court(projet)
        if urgence is not None:
            t["urgence"] = _check_urgence(urgence)
        t["modifie_le"] = _now()
        _write(data)
    return t


def supprimer(task_id: str) -> Dict[str, Any]:
    with _locked(exclusive=True):
        data = _read()
        t = _find(data, task_id)
        data["taches"] = [x for x in data["taches"] if x is not t]
        _write(data)
    return t


def dates_du_texte(texte: str):
    """« Dentiste 2026-10-27 14h » -> ("2026-10-27", "14:00") : pour l'ajout rapide depuis le site."""
    d = re.search(r"\b(20\d\d-[01]\d-[0-3]\d)\b", texte)
    h = re.search(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)?\b", texte)
    heure = f"{int(h.group(1)):02d}:{h.group(2) or '00'}" if h and d else None
    return (d.group(1) if d else None), heure
