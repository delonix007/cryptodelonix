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
    # Cek apakah file json ada (untuk lokal) atau pakai env (untuk github actions)
    if os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json") 
        firebase_admin.initialize_app(cred)
    else:
        print("Peringatan: File firebase_key.json tidak ditemukan.")

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
    
    # Ambil data airdrop yang 'Active'
    try:
        docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    except Exception as e:
        print(f"Gagal koneksi database: {e}")
        return

    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        source_channel = data.get('source')
        
        # Ambil keyword, fallback ke nama project jika kosong
        search_keyword = data.get('search_keyword', project_name)
        last_saved_msg = data.get('last_message_snippet', '')

        print(f"Mencari keyword '{search_keyword}' (termasuk reply) di @{source_channel}...")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # PERUBAHAN DISINI:
            # Kita tidak cari 'tgme_widget_message_text' saja.
            # Kita cari 'tgme_widget_message_wrap' (Balon Chat Utuh)
            # Ini akan mengambil Teks Reply + Teks Pesan Baru sekaligus.
            messages = soup.find_all('div', class_='tgme_widget_message_wrap')
            
            if not messages:
                print("Tidak ada pesan ditemukan.")
                continue

            # Ambil pesan paling terakhir
            latest_msg_obj = messages[-1]
            
            # .get_text() pada wrapper akan mengambil SEMUA teks di dalamnya
            # Termasuk teks reply ("Replying to...") dan teks pesan baru.
            full_text_context = latest_msg_obj.get_text(separator=' ', strip=True)
            full_text_lower = full_text_context.lower()

            # Logic Pencarian
            if search_keyword.lower() in full_text_lower:
                
                # Cek apakah ini pesan yang sama dengan sebelumnya (Anti-Spam)
                # Kita bandingkan 100 karakter pertama agar efisien
                current_snippet = full_text_context[:100]
                saved_snippet = last_saved_msg[:100]

                if current_snippet != saved_snippet:
                    print(f"--> UPDATE DITEMUKAN untuk {project_name} (Via Reply/Direct)!")
                    
                    # Kita coba bersihkan teks untuk notifikasi agar rapi
                    # Ambil teks utama saja untuk ditampilkan di notif (opsional)
                    main_text_div = latest_msg_obj.find('div', class_='tgme_widget_message_text')
                    display_text = main_text_div.get_text() if main_text_div else full_text_context
                    
                    alert_msg = (
                        f"🚨 **UPDATE DETECTED!** 🚨\n\n"
                        f"💎 **Project:** {project_name}\n"
                        f"🔍 **Keyword Found:** {search_keyword}\n"
                        f"📢 **Source:** @{source_channel}\n\n"
                        f"📜 **Pesan Update:**\n{display_text[:300]}...\n\n"
                        f"_(Keyword ditemukan dalam konteks pesan/reply)_"
                    )
                    
                    send_telegram_alert(alert_msg)
                    
                    # Simpan snippet baru ke database
                    doc.reference.update({'last_message_snippet': full_text_context})
                else:
                    print("--> Pesan (termasuk reply) sudah pernah dikirim. Skip.")
            else:
                pass 
                # print(f"Keyword tidak ditemukan di pesan terakhir.")

        except Exception as e:
            print(f"Error pada {project_name}: {e}")

if __name__ == "__main__":
    check_updates()
