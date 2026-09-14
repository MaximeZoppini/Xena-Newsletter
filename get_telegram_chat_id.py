import requests
import sys
from config import TELEGRAM_BOT_TOKEN

def get_latest_chat_id():
    token = sys.argv[1] if len(sys.argv) > 1 else TELEGRAM_BOT_TOKEN
    if not token:
        print("Erreur: TELEGRAM_BOT_TOKEN non spécifié.")
        return None
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    resp = requests.get(url).json()
    if not resp.get("ok"):
        print("Erreur API Telegram:", resp)
        return None
    results = resp.get("result", [])
    if not results:
        print("Aucun message reçu pour l'instant. Envoie un message au bot sur Telegram d'abord !")
        return None
    last_msg = results[-1]
    chat = last_msg.get("message", {}).get("chat", {}) or last_msg.get("my_chat_member", {}).get("chat", {})
    chat_id = chat.get("id")
    username = chat.get("username", "") or chat.get("first_name", "")
    print(f"Trouvé Chat ID: {chat_id} (Utilisateur: {username})")
    return chat_id

if __name__ == "__main__":
    get_latest_chat_id()
