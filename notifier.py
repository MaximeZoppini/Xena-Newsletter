import os
import json
import urllib.parse
import requests
import html
import logging
from typing import Dict, Any, Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CARDS_DIR
from card_generator import generate_entity_card

logger = logging.getLogger("notifier")

STYLE_LABELS = {
    "contradiction": "Contradiction (Révélation vs Défense)",
    "deroule_brut": "Déroulé brut chronologique",
    "insider": "Insider direct"
}

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
    domain = analysis.get("target_domain")
    style_key = analysis.get("chosen_style", "")
    style_label = STYLE_LABELS.get(style_key, style_key.capitalize())

    safe_title = html.escape(item['title'])
    safe_source = html.escape(item['source'])
    safe_core = html.escape(analysis.get("factual_core", ""))
    safe_bias = html.escape(analysis.get("framing_detected", ""))
    safe_counter = html.escape(analysis.get("counter_view", "Non spécifié"))
    safe_quote = html.escape(analysis.get("source_quote", ""))
    safe_tweet = html.escape(tweet_text)

    score_badge = "🔥 RÉVÉLATION MAJEURE" if score >= 8.8 else "⚡ IMPACT FACTUEL"

    # Layout : Tweet en haut prêt à copier, analyse complète repliée
    caption_text = (
        f"{score_badge} (Score : <b>{score}/10</b>) • <i>{safe_source}</i>\n"
        f"📰 <b>{safe_title}</b>\n\n"
        f"✍️ <b>Tweet proposé :</b> <i>(tap pour copier)</i>\n"
        f"<code>{safe_tweet}</code>\n\n"
        f"<blockquote expandable>📊 <b>Analyse de Xena :</b>\n"
        f"• Format choisi : <b>{style_label}</b>\n"
        f"• Impact : <b>{impact}/10</b> | Inédit : <b>{novelty}/10</b> | Preuves : <b>{evidence}/10</b>\n\n"
        f"🔍 <b>Fait brut vérifié :</b>\n{safe_core}\n\n"
        f"⚖️ <b>Cadrage & Contradictoire :</b>\n"
        f"• <i>Angle source</i> : {safe_bias}\n"
        f"• <i>Réponse / Nuance</i> : {safe_counter}\n\n"
        f"📌 <b>Citation source :</b>\n<i>« {safe_quote} »</i></blockquote>"
    )

    if len(caption_text) > 1020:
        caption_text = caption_text[:1000] + "...</blockquote>"

    inline_keyboard = {
        "inline_keyboard": [
            [
                {"text": "🐦 VALIDER SUR X (1 CLIC)", "url": twitter_intent_url}
            ],
            [
                {"text": "🔗 LIRE L'ARTICLE SOURCE", "url": item["url"]}
            ],
            [
                {"text": "✅ Tweeté / Validé", "callback_data": f"fb:ok:{item['id']}"},
                {"text": "❌ Rejeter", "callback_data": f"fb:no:{item['id']}"}
            ]
        ]
    }

    silent_mode = bool(score < 8.8)

    # 1. Générer et envoyer avec la carte logo pure
    try:
        card_file = generate_entity_card(item["id"], domain, CARDS_DIR)
        photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        
        with open(card_file, "rb") as f:
            resp = requests.post(photo_url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption_text,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(inline_keyboard),
                "disable_notification": silent_mode
            }, files={"photo": f}, timeout=10)
            
            if resp.json().get("ok"):
                logger.info(f"Alerte envoyée pour : {item['title']} (Style: {style_label})")
                return True
    except Exception as e:
        logger.warning(f"Erreur envoi carte logo ({e}), repli sur message texte.")

    # 2. Fallback message texte si échec image
    text_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": caption_text,
        "parse_mode": "HTML",
        "reply_markup": inline_keyboard,
        "disable_notification": silent_mode
    }

    try:
        resp = requests.post(text_url, json=payload, timeout=10)
        return resp.json().get("ok", False)
    except Exception as e:
        logger.error(f"Exception envoi Telegram: {e}")
        return False

def process_telegram_feedback(storage, offset: int = 0) -> int:
    if not TELEGRAM_BOT_TOKEN:
        return offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=1"
        resp = requests.get(url, timeout=3).json()
        if not resp.get("ok"):
            return offset
            
        for update in resp.get("result", []):
            offset = max(offset, update["update_id"] + 1)
            cb = update.get("callback_query")
            if not cb:
                continue
                
            data = cb.get("data", "")
            if data.startswith("fb:"):
                _, action, art_id = data.split(":", 2)
                act_label = "tweeted" if action == "ok" else "rejected"
                storage.log_feedback(art_id, act_label)
                logger.info(f"Feedback enregistré : {art_id} -> {act_label}")
                
                ans_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                msg = "✅ Noté comme Tweeté sur X !" if action == "ok" else "❌ Noté comme Rejeté."
                requests.post(ans_url, json={"callback_query_id": cb["id"], "text": msg}, timeout=3)
    except Exception as e:
        logger.debug(f"Erreur polling feedback: {e}")
    return offset

def notify(item: Dict[str, Any], analysis: Dict[str, Any]):
    return send_telegram_notification(item, analysis)
