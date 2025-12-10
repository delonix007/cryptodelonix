import os
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# --- KONFIGURASI ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Inisialisasi Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json") 
    firebase_admin.initialize_app(cred)

db = firestore.client()

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal kirim telegram: {e}")

def check_updates():
    print("Memulai pengecekan update...")
    # Ambil data yang statusnya Active saja
    docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    
    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        source_channel = data.get('source')
        # Ambil pesan terakhir yang tersimpan di DB (kalau belum ada, anggap kosong)
        last_saved_msg = data.get('last_message_snippet', '')

        print(f"Checking: {project_name} di {source_channel}...")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Ambil pesan TERBARU saja (paling bawah di halaman t.me/s/)
            messages = soup.find_all('div', class_='tgme_widget_message_text')
            
            if not messages:
                continue

            # Kita ambil pesan paling terakhir (paling baru)
            latest_msg_obj = messages[-1]
            latest_text = latest_msg_obj.get_text().strip() # Teks asli
            latest_text_lower = latest_text.lower() # Teks huruf kecil untuk pencarian

            # LOGIKA PENTING:
            # 1. Cek apakah nama project ada di pesan
            # 2. Cek apakah pesan ini BEDA dengan yang terakhir disimpan (Anti-Spam)
            if project_name.lower() in latest_text_lower:
                if latest_text != last_saved_msg:
                    print(f"--> UPDATE DITEMUKAN untuk {project_name}!")
                    
                    # 1. Kirim Notif
                    alert_msg = (
                        f"🚨 **UPDATE DETECTED!** 🚨\n\n"
                        f"💎 **Project:** {project_name}\n"
                        f"📢 **Source:** @{source_channel}\n\n"
                        f"📜 **Isi Pesan:**\n{latest_text[:200]}..." # Cuplik 200 huruf
                    )
                    send_telegram_alert(alert_msg)
                    
                    # 2. Update Database dengan pesan baru agar tidak spam nanti
                    doc.reference.update({'last_message_snippet': latest_text})
                else:
                    print(f"--> Ada mention {project_name}, tapi pesan sudah pernah dikirim. Skip.")
            
        except Exception as e:
            print(f"Error pada {project_name}: {e}")

if __name__ == "__main__":
    check_updates()
