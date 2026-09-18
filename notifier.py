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
    "contradiction": "Contradiction (Leak vs Official Defense)",
    "deroule_brut": "Raw Breakdown",
    "insider": "Direct Insider"
}

def send_telegram_notification(item: Dict[str, Any], analysis: Dict[str, Any]) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
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

    safe_title = html.escape(item['title'][:75])
    safe_source = html.escape(item['source'])
    safe_core = html.escape(analysis.get("factual_core", "")[:100])
    safe_bias = html.escape(analysis.get("framing_detected", "")[:60])
    safe_counter = html.escape(analysis.get("counter_view", "Unspecified")[:70])
    safe_quote = html.escape(analysis.get("source_quote", "")[:80])
    safe_tweet = html.escape(tweet_text)
    article_url = item.get("url", "").strip()
    safe_url = html.escape(article_url)

    score_badge = "🔥 MAJOR REVELATION" if score >= 8.8 else "⚡ FACTUAL IMPACT"

    # Layout optimisé pour l'algorithme X :
    # Post 1 : Texte pur + Image (zéro lien dans le tweet pour reach max)
    # Post 2 : Lien source posté en réponse au tweet
    caption_text = (
        f"{score_badge} (Score: <b>{score}/10</b>) • <i>{safe_source}</i>\n"
        f"📰 <b>{safe_title}</b>\n\n"
        f"✍️ <b>Tweet 1 (Post principal) :</b> <i>(tap pour copier)</i>\n"
        f"<code>{safe_tweet}</code>\n\n"
        f"🔗 <b>Tweet 2 (Lien en réponse) :</b> <i>(tap pour copier)</i>\n"
        f"<code>{safe_url}</code>\n\n"
        f"<blockquote expandable>📊 <b>Xena Breakdown:</b>\n"
        f"• Style: <b>{style_label}</b>\n"
        f"• Impact: <b>{impact}/10</b> | Scoop: <b>{novelty}/10</b> | Preuves: <b>{evidence}/10</b>\n\n"
        f"🔍 <b>Fait :</b> {safe_core}\n"
        f"⚖️ <b>Angle :</b> {safe_bias}\n"
        f"📌 <b>Citation :</b> <i>« {safe_quote} »</i></blockquote>"
    )

    # Sécurité absolue : Telegram sendPhoto refuse les légendes > 1024 caractères.
    if len(caption_text) > 980:
        caption_text = (
            f"{score_badge} (Score: <b>{score}/10</b>) • <i>{safe_source}</i>\n"
            f"📰 <b>{safe_title}</b>\n\n"
            f"✍️ <b>Tweet 1 (Post principal) :</b> <i>(tap pour copier)</i>\n"
            f"<code>{safe_tweet}</code>\n\n"
            f"🔗 <b>Tweet 2 (Lien en réponse) :</b> <i>(tap pour copier)</i>\n"
            f"<code>{safe_url}</code>\n\n"
            f"<blockquote expandable>📊 <b>Xena Breakdown:</b>\n"
            f"🔍 <b>Fait :</b> {safe_core}\n"
            f"📌 <b>Citation :</b> <i>« {safe_quote} »</i></blockquote>"
        )

    buttons = [
        [
            {"text": "🐦 Tweet 1 : Ouvrir X (1 clic)", "url": twitter_intent_url}
        ]
    ]

    # Bouton natif Telegram de copie directe dans le presse-papier
    if article_url and len(article_url) <= 256:
        buttons.append([
            {"text": "📋 Copier le lien source (Tweet 2)", "copy_text": {"text": article_url}}
        ])

    buttons.append([
        {"text": "🔗 Ouvrir l'article original", "url": article_url}
    ])

    buttons.append([
        {"text": "✅ Tweeté / Validé", "callback_data": f"fb:ok:{item['id']}"},
        {"text": "❌ Rejeter", "callback_data": f"fb:no:{item['id']}"}
    ])

    inline_keyboard = {"inline_keyboard": buttons}

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
            
            data = resp.json()
            if data.get("ok"):
                logger.info(f"Alerte envoyée pour : {item['title']} (Style: {style_label})")
                return True
            else:
                logger.warning(f"Telegram sendPhoto refusé: {data.get('description')}")
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
        data = resp.json()
        if data.get("ok"):
            return True
        logger.error(f"Telegram sendMessage refusé: {data.get('description')}")
        return False
    except Exception as e:
        logger.error(f"Exception envoi Telegram: {e}")
        return False

def process_telegram_updates(storage, analyzer, offset: int = 0) -> int:
    if not TELEGRAM_BOT_TOKEN:
        return offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=2"
        resp = requests.get(url, timeout=4).json()
        if not resp.get("ok"):
            return offset
            
        for update in resp.get("result", []):
            offset = max(offset, update["update_id"] + 1)
            
            # 1. Gestion des clics sur les boutons de feedback
            cb = update.get("callback_query")
            if cb:
                data = cb.get("data", "")
                if data.startswith("fb:"):
                    _, action, art_id = data.split(":", 2)
                    act_label = "tweeted" if action == "ok" else "rejected"
                    storage.log_feedback(art_id, act_label)
                    logger.info(f"Feedback enregistré : {art_id} -> {act_label}")
                    
                    ans_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                    msg = "✅ Marked as Tweeted on X!" if action == "ok" else "❌ Marked as Rejected."
                    requests.post(ans_url, json={"callback_query_id": cb["id"], "text": msg}, timeout=3)
                continue

            # 2. Gestion des messages textes entrants (Tweets à répondre)
            msg = update.get("message")
            if msg and msg.get("text"):
                chat_id = msg["chat"]["id"]
                text = msg["text"].strip()
                
                # Sécurité : filtrer sur l'ID autorisé si spécifié
                if TELEGRAM_CHAT_ID and str(chat_id) != str(TELEGRAM_CHAT_ID):
                    logger.warning(f"Message reçu d'un chat non autorisé ({chat_id}) ignoré.")
                    continue
                
                if text.startswith("/start"):
                    welcome_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    requests.post(welcome_url, json={
                        "chat_id": chat_id,
                        "text": "👋 <b>Xena Ghostwriter</b> est prête. Envoie-moi le texte d'un tweet et je te génère une réponse affûtée.",
                        "parse_mode": "HTML"
                    }, timeout=3)
                    continue
                
                logger.info(f"Tweet reçu pour ghostwriting ({len(text)} chars). Génération en cours...")
                
                # Signal visuel Telegram "en train d'écrire..."
                action_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendChatAction"
                requests.post(action_url, json={"chat_id": chat_id, "action": "typing"}, timeout=2)
                
                # Génération par Gemini
                reply = analyzer.generate_tweet_reply(text)
                if reply:
                    encoded_reply = urllib.parse.quote(reply)
                    twitter_reply_url = f"https://twitter.com/intent/tweet?text={encoded_reply}"
                    
                    send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    payload = {
                        "chat_id": chat_id,
                        "text": f"✍️ <b>Suggested Reply:</b> <i>(tap to copy)</i>\n\n<code>{html.escape(reply)}</code>",
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": [
                                [{"text": "🐦 POST REPLY ON X (1 CLICK)", "url": twitter_reply_url}]
                            ]
                        }
                    }
                    requests.post(send_url, json=payload, timeout=5)
                    logger.info(f"Réponse ghostwriter envoyée ({len(reply)} caractères)")
                else:
                    err_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                    requests.post(err_url, json={
                        "chat_id": chat_id,
                        "text": "⚠️ Erreur lors de la génération de la réponse.",
                    }, timeout=3)

    except Exception as e:
        logger.debug(f"Erreur polling updates: {e}")
    return offset

# Alias pour compatibilité
process_telegram_feedback = process_telegram_updates

def notify(item: Dict[str, Any], analysis: Dict[str, Any]):
    return send_telegram_notification(item, analysis)
