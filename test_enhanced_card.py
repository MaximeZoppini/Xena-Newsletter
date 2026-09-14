import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

def download_logo(domain: str) -> Image.Image:
    url = f"https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://{domain}&size=256"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        logo = Image.open(resp).convert("RGBA")
        return logo

def create_enhanced_card(domain: str, entity_name: str, source: str, headline: str, score: float, out_path: str = "/tmp/enhanced_card.png"):
    width, height = 1200, 675
    # Fond sombre moderne
    img = Image.new("RGBA", (width, height), (11, 15, 23, 255))
    draw = ImageDraw.Draw(img)

    # 1. Halo lumineux subtil (radial glow) au centre
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_color = (56, 189, 248, 45) if score < 8.8 else (245, 158, 11, 55) # Cyan ou Or
    cx, cy = width // 2, height // 2 - 30
    for r in range(260, 40, -20):
        alpha = int((1 - (r / 260)) * glow_color[3])
        glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(glow_color[0], glow_color[1], glow_color[2], alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(30))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # 2. Header minimaliste
    try:
        font_tag = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 22)
        font_score = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 24)
        font_headline = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 36)
        font_entity = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 26)
    except Exception:
        font_tag = font_score = font_headline = font_entity = ImageFont.load_default()

    # Tag Source en haut à gauche
    draw.rounded_rectangle([60, 45, 340, 95], radius=8, fill="#161e2e", outline="#1e293b", width=1)
    draw.text((80, 58), f"XENA • {source.upper()}", fill="#94a3b8", font=font_tag)

    # Tag Score en haut à droite
    score_badge_color = "#d97706" if score >= 8.8 else "#0284c7"
    draw.rounded_rectangle([width - 240, 45, width - 60, 95], radius=8, fill=score_badge_color)
    draw.text((width - 215, 57), f"INDICE {score:.1f}", fill="#ffffff", font=font_score)

    # 3. Macaron central pour le logo de l'entité
    logo = download_logo(domain)
    # Redimensionner le logo proprement
    logo_size = 180
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
    
    # Boîte arrondie centrale
    box_size = 240
    bx1, by1 = cx - box_size // 2, cy - box_size // 2
    bx2, by2 = cx + box_size // 2, cy + box_size // 2
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=36, fill="#0f172a", outline="#334155", width=2)

    # Coller le logo au centre de la boîte
    lx = cx - logo.width // 2
    ly = cy - logo.height // 2
    img.paste(logo, (lx, ly), logo if logo.mode == 'RGBA' else None)

    # 4. Nom de l'entité sous le logo
    bbox_e = draw.textbbox((0, 0), entity_name.upper(), font=font_entity)
    ew = bbox_e[2] - bbox_e[0]
    draw.text((cx - ew // 2, by2 + 25), entity_name.upper(), fill="#38bdf8", font=font_entity)

    # 5. Titre choc en 1 seule ligne en bas
    bbox_h = draw.textbbox((0, 0), headline, font=font_headline)
    hw = bbox_h[2] - bbox_h[0]
    draw.text((cx - hw // 2, height - 90), headline, fill="#f8fafc", font=font_headline)

    img.convert("RGB").save(out_path, format="PNG")
    return out_path

if __name__ == "__main__":
    create_enhanced_card("xbox.com", "Xbox", "Mediapart", "Fuite massive de données de télémétrie", 8.6)
    print("Enhanced card created at /tmp/enhanced_card.png")
