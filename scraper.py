import os
import requests
import re
import time
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# --- KONFIGURASI ---
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

if not firebase_admin._apps:
    if os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json") 
        firebase_admin.initialize_app(cred)
    else:
        # Fallback jika pakai ENV variable encoded base64/json langsung
        firebase_admin.initialize_app()

db = firestore.client()

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal kirim telegram: {e}")

def extract_id_from_url(url_string):
    """Mengambil ID angka dari link t.me"""
    if not url_string: return None
    match = re.search(r'/(\d+)(\?|$)', url_string)
    return match.group(1) if match else None

def check_updates():
    print("--- MULAI DEEP SCRAPING ---")
    
    try:
        docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    except Exception as e:
        print(f"Error Koneksi Database: {e}")
        return

    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name', 'Unknown')
        source_channel = data.get('source', '')
        
        # KEYPOINT: Pastikan tracked_msg_id selalu String untuk perbandingan
        tracked_msg_id = str(data.get('tracked_msg_id', ''))
        search_keyword = data.get('search_keyword', '').lower()
        
        if not source_channel: continue

        print(f"\n🔍 Cek: {project_name} (@{source_channel}) | TrackID: {tracked_msg_id}")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            # User Agent agar tidak diblokir Telegram Web
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            r = requests.get(url, headers=headers, timeout=30)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # AMBIL 30 PESAN TERAKHIR (Lebih banyak dari sebelumnya)
            messages = soup.find_all('div', class_='tgme_widget_message_wrap')
            if not messages:
                print("   ⚠️ Channel tidak ditemukan atau kosong.")
                continue

            recent_messages = messages[-30:] # Scan 30 pesan terakhir

            for msg_wrap in recent_messages:
                msg_div = msg_wrap.find('div', class_='tgme_widget_message')
                if not msg_div: continue
                
                # 1. ID Pesan Saat Ini
                post_link = msg_div.get('data-post')
                current_msg_id = extract_id_from_url(post_link)
                if not current_msg_id: continue

                # Skip jika pesan ini lebih lama/sama dengan yang sudah dilacak (Logic ID Increment)
                # Hanya valid jika tracked_msg_id berisi angka valid
                if tracked_msg_id.isdigit() and current_msg_id.isdigit():
                    if int(current_msg_id) <= int(tracked_msg_id):
                        continue

                # 2. Ambil Text
                text_div = msg_wrap.find('div', class_='tgme_widget_message_text')
                raw_text = text_div.get_text(separator=' ', strip=True) if text_div else "[Media/Foto]"
                text_lower = raw_text.lower()

                # 3. Cek Reply ID
                reply_div = msg_wrap.find('a', class_='tgme_widget_message_reply')
                reply_to_id = None
                if reply_div:
                    reply_href = reply_div.get('href')
                    reply_to_id = extract_id_from_url(reply_href)

                # --- MATCHING LOGIC (STRING to STRING) ---
                is_match = False
                match_reason = ""

                # Cek Reply (Pastikan kedua sisi adalah STRING)
                if tracked_msg_id and reply_to_id and str(reply_to_id) == str(tracked_msg_id):
                    is_match = True
                    match_reason = f"Reply ke Post Utama ({tracked_msg_id})"
                
                # Cek Keyword
                elif search_keyword and search_keyword in text_lower:
                    is_match = True
                    match_reason = f"Keyword '{search_keyword}' ditemukan"

                if is_match:
                    print(f"   ✅ HIT! ID: {current_msg_id} | {match_reason}")
                    
                    msg = (
                        f"🚨 **UPDATE: {project_name}**\n"
                        f"Info: {match_reason}\n\n"
                        f"_{raw_text[:300]}..._\n\n"
                        f"[Buka Pesan](https://t.me/{source_channel}/{current_msg_id})"
                    )
                    send_telegram_alert(msg)
                    
                    # AUTO SWITCH ID: Pindah pantauan ke pesan baru ini
                    doc.reference.update({
                        'tracked_msg_id': str(current_msg_id),
                        'last_message_snippet': raw_text[:50]
                    })
                    
                    # Update local var agar tidak spam notif di loop yang sama
                    tracked_msg_id = str(current_msg_id)

        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    check_updates()
