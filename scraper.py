import os
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Konfigurasi Telegram
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# 2. Inisialisasi Firebase (Pakai Key dari Secrets GitHub)
cred = credentials.Certificate("firebase_key.json") 
firebase_admin.initialize_app(cred)
db = firestore.client()

# 3. Logika Scraper
def check_updates():
    # Ambil semua airdrop yang statusnya 'Active'
    docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    
    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        channel_username = data.get('source') # misal: airdropfinder
        
        print(f"Checking {project_name} on {channel_username}...")
        
        # Kita pakai trik 't.me/s/' untuk baca channel public tanpa login akun user
        url = f"https://t.me/s/{channel_username}"
        
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Ambil 5 pesan terakhir
            messages = soup.find_all('div', class_='tgme_widget_message_text', limit=5)
            
            for msg in messages:
                text = msg.get_text().lower()
                # Cek apakah nama project disebut di pesan tersebut
                if project_name.lower() in text:
                    # Sederhana: Kita kirim notif bahwa ada mention
                    # (Untuk sistem canggih butuh simpan 'last_checked_id' agar tidak spam)
                    
                    alert_msg = f"🔔 **UPDATE DETECTED!**\n\nProject: {project_name}\nSource: @{channel_username}\n\nCek sekarang!"
                    # Di sini idealnya ada logika cek apakah pesan ini sudah dikirim sebelumnya
                    # Tapi untuk MVP (Minimum Viable Product), kita biarkan dulu.
                    
                    # send_telegram_alert(alert_msg) 
                    # Uncomment baris atas jika ingin test, tapi hati-hati spam jika cronjob jalan terus.
                    # Solusi anti-spam sederhana:
                    print(f"Update found for {project_name}")
                    
        except Exception as e:
            print(f"Error checking {project_name}: {e}")

if __name__ == "__main__":
    check_updates()
