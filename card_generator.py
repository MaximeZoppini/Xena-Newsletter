import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Optional

def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        bbox = draw.textbbox((0, 0), " ".join(current_line), font=font)
        if bbox[2] - bbox[0] > max_width:
            current_line.pop()
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def generate_branded_card(
    article_id: str,
    title: str,
    source: str,
    score: float,
    output_dir: str = "data/cards"
) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    out_path = os.path.join(output_dir, f"{article_id}.png")

    width, height = 1200, 675
    # Fond sombre moderne (charcoal / midnight slate)
    img = Image.new("RGB", (width, height), color="#0c1017")
    draw = ImageDraw.Draw(img)

    # 1. Bordure discrète & Grille décorative
    draw.rectangle([20, 20, width - 20, height - 20], outline="#1f2937", width=2)
    draw.line([(20, 110), (width - 20, 110)], fill="#1f2937", width=2)
    draw.line([(20, height - 90), (width - 20, height - 90)], fill="#1f2937", width=2)

    # 2. Header : Marque Xena
    font_brand = get_font(32, bold=True)
    draw.text((60, 48), "XENA", fill="#ffffff", font=font_brand)
    font_sub = get_font(20, bold=False)
    draw.text((165, 58), "•  IA D'INVESTIGATION INDÉPENDANTE", fill="#9ca3af", font=font_sub)

    # Badge Score à droite
    score_bg = "#b45309" if score >= 8.8 else "#1e3a8a"
    draw.rounded_rectangle([width - 260, 40, width - 60, 92], radius=10, fill=score_bg)
    font_score = get_font(24, bold=True)
    score_label = f"INDICE {score:.1f}/10"
    draw.text((width - 240, 52), score_label, fill="#ffffff", font=font_score)

    # 3. Source Tag
    font_source = get_font(22, bold=True)
    draw.text((60, 150), f"ENQUÊTE • {source.upper()}", fill="#38bdf8", font=font_source)

    # 4. Titre / Fait Principal (Gros caractères au centre)
    font_title = get_font(42, bold=True)
    lines = wrap_text(title, font_title, width - 140, draw)[:5]
    y_text = 210
    for line in lines:
        draw.text((60, y_text), line, fill="#f3f4f6", font=font_title)
        y_text += 58

    # 5. Footer Signature
    font_foot = get_font(20, bold=False)
    draw.text((60, height - 60), "⚖️ Fait brut vérifié • Zéro avis • Version de l'accusé incluse", fill="#6b7280", font=font_foot)
    draw.text((width - 250, height - 60), "xena-investigation.io", fill="#4b5563", font=font_foot)

    img.save(out_path, format="PNG")
    return out_path

if __name__ == "__main__":
    generate_branded_card("test_card", "Affaire des diurétiques au ministère de la Culture : dix ans d'alertes ignorées", "Mediapart", 8.4)
    print("Test card generated successfully.")
