import urllib.parse
import requests
import html
import logging
from typing import Dict, Any, Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("notifier")

def send_telegram_notification(item: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        return False

    tweet_text = analysis.get("tweet_text", "").strip()
    encoded_tweet = urllib.parse.quote(tweet_text)
    twitter_intent_url = f"https://twitter.com/intent/tweet?text={encoded_tweet}"

    score = analysis.get("global_score", 0.0)
    impact = analysis.get("systemic_impact", 0)
    novelty = analysis.get("novelty_scoop", 0)
    evidence = analysis.get("evidence_quality", 0)

    safe_title = html.escape(item['title'])
    safe_source = html.escape(item['source'])
    safe_core = html.escape(analysis.get("factual_core", ""))
    safe_bias = html.escape(analysis.get("framing_detected", ""))
    safe_counter = html.escape(analysis.get("counter_view", "Non spécifié"))
    safe_tweet = html.escape(tweet_text)

    score_badge = "🔥 RÉVÉLATION MAJEURE" if score >= 8.8 else "⚡ IMPACT FACTUEL"

    # Layout ergonomique : Tweet tout en haut, analyse repliée en dessous
    caption_text = (
        f"{score_badge} (Score : <b>{score}/10</b>) • <i>{safe_source}</i>\n"
        f"📰 <b>{safe_title}</b>\n\n"
        f"✍️ <b>Tweet prêt à publier :</b> <i>(tap pour copier)</i>\n"
        f"<code>{safe_tweet}</code>\n\n"
        f"<blockquote expandable>📊 <b>Analyse de Xena (Pourquoi cette actu) :</b>\n"
        f"• Impact : <b>{impact}/10</b> | Inédit : <b>{novelty}/10</b> | Preuves : <b>{evidence}/10</b>\n\n"
        f"🔍 <b>Fait brut vérifié :</b>\n{safe_core}\n\n"
        f"⚖️ <b>Cadrage & Contradictoire :</b>\n"
        f"• <i>Angle source</i> : {safe_bias}\n"
        f"• <i>Réponse / Nuance</i> : {safe_counter}</blockquote>"
    )

    # Tronquer si la légende dépasse la limite Telegram de 1024 caractères
    if len(caption_text) > 1020:
        caption_text = caption_text[:1000] + "...</blockquote>"

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "🐦 VALIDER SUR X (1 CLIC)", "url": twitter_intent_url}
            ],
            [
                {"text": "🔗 LIRE L'ARTICLE SOURCE", "url": item["url"]}
            ]
        ]
    }

    # Ne fait sonner le téléphone que pour les séismes majeurs (>= 8.8)
    silent_mode = bool(score < 8.8)
    image_url = item.get("image_url")

    # 1. Tentative d'envoi avec photo
    if image_url and image_url.startswith("http"):
        photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": image_url,
            "caption": caption_text,
            "parse_mode": "HTML",
            "reply_markup": inline_keyboard,
            "disable_notification": silent_mode
        }
        try:
            resp = requests.post(photo_url, json=payload, timeout=8)
            if resp.json().get("ok"):
                logger.info(f"Photo Telegram envoyée pour : {item['title']}")
                return True
        except Exception as e:
            logger.warning(f"Échec envoi photo ({e}), bascule vers message texte.")

    # 2. Fallback message texte si pas d'image ou erreur photo
    text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": caption_text,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_notification": silent_mode,
        "disable_web_page_preview": False
    }

    try:
        resp = requests.post(text_url, json=payload, timeout=10)
        res_data = resp.json()
        if res_data.get("ok"):
            logger.info(f"Notification Telegram envoyée pour : {item['title']}")
            return True
        else:
            logger.error(f"Erreur Telegram: {res_data}")
            return False
    except Exception as e:
        logger.error(f"Exception lors de l'envoi Telegram: {e}")
        return False

def notify(item: Dict[str, Any], analysis: Dict[str, Any]):
    return send_telegram_notification(item, analysis)
