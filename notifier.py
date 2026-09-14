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
    score = analysis.get("interest_score", 7)

    safe_title = html.escape(item['title'])
    safe_source = html.escape(item['source'])
    safe_core = html.escape(analysis.get("factual_core", ""))
    safe_bias = html.escape(analysis.get("framing_bias", ""))
    safe_tweet = html.escape(tweet_text)

    text = (
        f"⭐ <b>x-newsletter</b> • Note : <b>{score}/10</b>\n"
        f"📰 <b>{safe_title}</b>\n"
        f"🏷️ Source : <i>{safe_source}</i>\n\n"
        f"🔍 <b>Fait Brut & Vérifié :</b>\n{safe_core}\n\n"
        f"⚖️ <b>Biais & Cadrage :</b>\n{safe_bias}\n\n"
        f"🐦 <b>Tweet proposé :</b>\n<code>{safe_tweet}</code>"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "🐦 TWEETER EN 1 CLIC", "url": twitter_intent_url}
            ],
            [
                {"text": "🔗 Voir la source", "url": item["url"]}
            ]
        ]
    }

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
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

def send_discord_notification(item: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    if not DISCORD_WEBHOOK_URL:
        return False

    tweet_text = analysis.get("tweet_text", "")
    encoded_tweet = urllib.parse.quote(tweet_text)
    twitter_intent_url = f"https://twitter.com/intent/tweet?text={encoded_tweet}"

    score = analysis.get("interest_score", 7)
    color = 0xF1C40F if score >= 9 else (0x2ECC71 if score >= 8 else 0x3498DB)

    embed = {
        "title": f"📰 {item['title'][:200]}",
        "url": item["url"],
        "color": color,
        "fields": [
            {
                "name": "🔍 Fait Brut & Vérification",
                "value": analysis.get("factual_core", "N/A")[:1000],
                "inline": False
            },
            {
                "name": f"⚖️ Biais & Cadrage ({item['source']})",
                "value": analysis.get("framing_bias", "N/A")[:500],
                "inline": False
            },
            {
                "name": "🐦 Tweet Proposé",
                "value": f"```\n{tweet_text}\n```",
                "inline": False
            },
            {
                "name": "🚀 Action Rapide",
                "value": f"👉 **[CLIQUER ICI POUR TWEETER EN 1 CLIC]({twitter_intent_url})**",
                "inline": False
            }
        ],
        "footer": {
            "text": f"x-newsletter • Score d'intérêt : {score}/10 • Source : {item['source']}"
        }
    }

    payload = {
        "username": "x-newsletter Curateur",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2965/2965879.png",
        "embeds": [embed]
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        return resp.status_code in [200, 204]
    except Exception as e:
        logger.error(f"Exception envoi Discord: {e}")
        return False

def notify(item: Dict[str, Any], analysis: Dict[str, Any]):
    sent_any = False
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        if send_telegram_notification(item, analysis):
            sent_any = True
    if DISCORD_WEBHOOK_URL:
        if send_discord_notification(item, analysis):
            sent_any = True
    return sent_any
