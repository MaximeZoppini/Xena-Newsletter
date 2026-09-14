import urllib.parse
import requests
import logging
from typing import Dict, Any
from config import DISCORD_WEBHOOK_URL

logger = logging.getLogger("notifier")

def send_discord_notification(item: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    if not DISCORD_WEBHOOK_URL:
        logger.warning("DISCORD_WEBHOOK_URL non configuré. Notification ignorée.")
        return False

    tweet_text = analysis.get("tweet_text", "")
    encoded_tweet = urllib.parse.quote(tweet_text)
    twitter_intent_url = f"https://twitter.com/intent/tweet?text={encoded_tweet}"

    score = analysis.get("interest_score", 7)
    # Couleur : Or (10), Vert (8-9), Bleu (7)
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
        if resp.status_code in [200, 204]:
            logger.info(f"Notification Discord envoyée avec succès pour : {item['title']}")
            return True
        else:
            logger.error(f"Erreur Discord Webhook ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Exception lors de l'envoi Discord: {e}")
        return False
