"""
Réglages modifiables sans toucher au code : valeurs par défaut dans reglages/*.txt,
surcharges enregistrées en base (table app_state) depuis la page Réglages du site.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple

from config import BASE_DIR
from storage import Storage

DEFAULTS_DIR = Path(BASE_DIR) / "reglages"
TEXTES = ("composants_critiques", "questions_negatives", "profil")


def _default(name: str) -> str:
    path = DEFAULTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_text(storage: Storage, name: str) -> str:
    value = storage.get_state(f"reglage:{name}")
    return value if value is not None else _default(name)


def set_text(storage: Storage, name: str, value: str):
    storage.set_state(f"reglage:{name}", value.strip() + "\n")


def lines(storage: Storage, name: str) -> List[str]:
    return [l.strip() for l in get_text(storage, name).splitlines() if l.strip() and not l.strip().startswith("#")]


def contradicteur_actif(storage: Storage) -> bool:
    return storage.get_state("reglage:contradicteur") != "0"


def set_contradicteur(storage: Storage, actif: bool):
    storage.set_state("reglage:contradicteur", "1" if actif else "0")


def composants(storage: Storage) -> List[Tuple[str, List[str]]]:
    """[(nom affiché, [synonymes])]"""
    out = []
    for line in lines(storage, "composants_critiques"):
        names = [n.strip() for n in line.split(",") if n.strip()]
        if names:
            out.append((names[0], names))
    return out


def composants_regex(storage: Storage) -> Optional[re.Pattern]:
    names = [n for _, syn in composants(storage) for n in syn]
    if not names:
        return None
    return re.compile(r"(?<![\w.])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])", re.IGNORECASE)


def composants_texte(storage: Storage) -> str:
    return ", ".join(" / ".join(syn) for _, syn in composants(storage)) or "(aucun)"


# Tolérance au bruit des notifications push : « exceptionnel » (méga-dingueries seulement) ou « important »
SEUILS_PUSH = ("exceptionnel", "important")


def seuil_push(storage: Storage) -> str:
    value = storage.get_state("reglage:seuil_push")
    return value if value in SEUILS_PUSH else "exceptionnel"


def set_seuil_push(storage: Storage, value: str):
    if value in SEUILS_PUSH:
        storage.set_state("reglage:seuil_push", value)
