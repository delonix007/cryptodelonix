import os
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# --- KONFIGURASI ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not firebase_admin._apps:
    if os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json") 
        firebase_admin.initialize_app(cred)

db = firestore.client()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    requests.post(url, json=payload)

def run_daily_reminder():
    print("Mengumpulkan data reminder harian...")
    
    # Ambil data yang isDailyReminder == True DAN status == Active
    docs = db.collection('airdrops').where('isDailyReminder', '==', True).where('status', '==', 'Active').stream()
    
    reminder_list = []
    
    for doc in docs:
        data = doc.to_dict()
        name = data.get('name', 'Unknown')
        link = data.get('link', '#')
        reminder_list.append(f"• [{name}]({link})")
    
    if reminder_list:
        # Susun Pesan
        text_body = "\n".join(reminder_list)
        msg = (
            f"🌞 **DAILY REMINDER GARAPAN** 🌞\n\n"
            f"Jangan lupa kerjakan task harian ini:\n\n"
            f"{text_body}\n\n"
            f"_Semangat JP!_ 🚀"
        )
        send_telegram(msg)
        print("Reminder terkirim!")
    else:
        print("Tidak ada garapan untuk diingatkan hari ini.")

if __name__ == "__main__":
    run_daily_reminder()
