import os
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from typing import Optional

def download_entity_logo(domain: str) -> Optional[Image.Image]:
    if not domain:
        return None
    url = f"https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://{domain}&size=256"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            img = Image.open(resp).convert("RGBA")
            return img
    except Exception:
        return None

def generate_entity_card(
    article_id: str,
    domain: Optional[str] = None,
    output_dir: str = "data/cards"
) -> str:
    """Génère une image épurée avec UNIQUEMENT le logo officiel au centre, sans AUCUN texte."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(output_dir, f"{article_id}.png")

    width, height = 1200, 675
    # Fond sombre moderne (charcoal / midnight)
    base = Image.new("RGBA", (width, height), (11, 15, 23, 255))
    cx, cy = width // 2, height // 2

    # 1. Halo lumineux subtil (lumière ambiante douce au centre)
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(280, 50, -25):
        alpha = int((1 - (r / 280)) * 40)
        glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(56, 189, 248, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(35))
    base = Image.alpha_composite(base, glow)

    # 2. Récupération et incrustation du logo
    logo = download_entity_logo(domain) if domain else None
    
    draw = ImageDraw.Draw(base)
    box_size = 280
    bx1, by1 = cx - box_size // 2, cy - box_size // 2
    bx2, by2 = cx + box_size // 2, cy + box_size // 2

    # Macaron arrondi élégant pour mettre en valeur l'icône
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=48, fill="#0f172a", outline="#1e293b", width=2)

    if logo:
        # Redimensionner le logo pour remplir harmonieusement le macaron
        max_logo_dim = 200
        logo.thumbnail((max_logo_dim, max_logo_dim), Image.Resampling.LANCZOS)
        lx = cx - logo.width // 2
        ly = cy - logo.height // 2
        base.paste(logo, (lx, ly), logo if logo.mode == 'RGBA' else None)

    # Sauvegarde finale en RGB
    base.convert("RGB").save(out_path, format="PNG")
    return out_path

if __name__ == "__main__":
    p = generate_entity_card("test_xbox_pure", "xbox.com", "/tmp")
    print(f"Pure logo card created at: {p}")
