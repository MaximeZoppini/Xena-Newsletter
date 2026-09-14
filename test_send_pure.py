import json
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from card_generator import generate_entity_card

p = generate_entity_card("test_xbox_final", "xbox.com", "data/cards")

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
caption = (
    "🔥 <b>XBOX</b> (Score : <b>8.6/10</b>) • <i>Mediapart</i>\n\n"
    "✍️ <b>Tweet prêt à publier :</b> <i>(tap pour copier)</i>\n"
    "<code>🎮 Selon une enquête de Mediapart, une faille dans l’infrastructure cloud de Xbox a exposé des métadonnées de télémétrie de millions d’utilisateurs sans consentement. Microsoft affirme avoir colmaté la vulnérabilité.\n\n"
    "🔗 https://mediapart.fr</code>\n\n"
    "<blockquote expandable>📊 <b>Analyse de Xena :</b>\n"
    "• Impact : <b>9/10</b> | Inédit : <b>8/10</b> | Preuves : <b>9/10</b>\n\n"
    "🔍 <b>Fait brut vérifié :</b>\n"
    "Une vulnérabilité sur les serveurs de télémétrie Xbox a permis l’accès non autorisé à des journaux de connexion.\n\n"
    "⚖️ <b>Cadrage & Contradictoire :</b>\n"
    "• Angle source : Enquête axée sur la protection de la vie privée des joueurs.\n"
    "• Réponse Microsoft : Le correctif a été déployé sous 48h, aucun mot de passe compromis.\n\n"
    "📌 <b>Citation source :</b>\n"
    "<i>« Les logs comprenaient les identifiants réseau et les temps de jeu effectifs. »</i></blockquote>"
)

inline_keyboard = {
    "inline_keyboard": [
        [{"text": "🐦 VALIDER SUR X (1 CLIC)", "url": "https://twitter.com/intent/tweet?text=Test"}],
        [{"text": "🔗 LIRE L'ARTICLE SOURCE", "url": "https://mediapart.fr"}],
        [{"text": "✅ Tweeté / Validé", "callback_data": "fb:ok:xbox_test"}, {"text": "❌ Rejeter", "callback_data": "fb:no:xbox_test"}]
    ]
}

with open(p, "rb") as f:
    resp = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(inline_keyboard)
    }, files={"photo": f})
    print("Telegram response:", resp.json().get("ok"))
