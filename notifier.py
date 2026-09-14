import urllib.parse
import requests
import html
import logging
from typing import Dict, Any, Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DISCORD_WEBHOOK_URL

logger = logging.getLogger("notifier")

def send_telegram_notification(item: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant.")
        return False

    tweet_text = analysis.get("tweet_text", "")
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

    score_badge = "🔥 RÉVÉLATION MAJEURE" if score >= 8.8 else "⚡ HAUT IMPACT FACTUEL"

    message_text = (
        f"👑 <b>Xena — Sélection Éditoriale</b>\n"
        f"────────────────────\n"
        f"{score_badge} • <b>Score : {score}/10</b>\n\n"
        f"📰 <b>Sujet :</b> {safe_title}\n"
        f"🏢 <b>Origine :</b> <i>{safe_source}</i>\n\n"
        f"📊 <b>Grille d'évaluation :</b>\n"
        f"• Impact systémique : <b>{impact}/10</b>\n"
        f"• Révélation / Inédit : <b>{novelty}/10</b>\n"
        f"• Solidité des preuves : <b>{evidence}/10</b>\n\n"
        f"🔍 <b>Le fait brut :</b>\n{safe_core}\n\n"
        f"⚖️ <b>Cadrage & Contradictoire :</b>\n"
        f"• <i>Angle source</i> : {safe_bias}\n"
        f"• <i>Réponse / Nuance</i> : {safe_counter}\n\n"
        f"🐦 <b>Proposition de Tweet (Impartial & Percutant) :</b>\n"
        f"<code>{safe_tweet}</code>\n"
        f"────────────────────\n"
        f"<i>Cliquez pour vérifier et publier en un instant sur X :</i>"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "🐦 VALIDER & TWEETER EN 1 CLIC", "url": twitter_intent_url}
            ],
            [
                {"text": "🔗 Examiner la source", "url": item["url"]}
            ]
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_web_page_preview": True
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        res_data = resp.json()
        if res_data.get("ok"):
            logger.info(f"Notification Telegram envoyée pour : {item['title']}")
            return True
        else:
            logger.error(f"Erreur Telegram ({resp.status_code}): {res_data}")
            return False
    except Exception as e:
        logger.error(f"Exception lors de l'envoi Telegram: {e}")
        return False

def notify(item: Dict[str, Any], analysis: Dict[str, Any]):
    return send_telegram_notification(item, analysis)
