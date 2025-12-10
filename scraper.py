import os
import requests
import re
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

db = firestore.client()

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Gagal kirim telegram: {e}")

def extract_message_id(url_or_string):
    """Mengambil angka ID dari link t.me/c/xxx/123 atau data-post"""
    if not url_or_string: return None
    match = re.search(r'/(\d+)$', url_or_string)
    return match.group(1) if match else None

def check_updates():
    print("Memulai pengecekan update (Mode Chain)...")
    
    try:
        docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    except Exception:
        return

    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        source_channel = data.get('source')
        search_keyword = data.get('search_keyword', project_name)
        
        # ID pesan terakhir yang kita anggap sebagai bagian dari topik ini
        tracked_msg_id = data.get('tracked_msg_id') 
        last_saved_snippet = data.get('last_message_snippet', '')

        print(f"Cek {project_name} (@{source_channel}) | Last ID: {tracked_msg_id}")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            r = requests.get(url, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Ambil semua pesan
            messages = soup.find_all('div', class_='tgme_widget_message_wrap')
            
            if not messages: continue

            # Loop dari pesan lama ke baru (agar urutan chain benar)
            # Kita hanya cek 5 pesan terakhir untuk efisiensi
            for msg_wrap in messages[-5:]:
                
                # 1. Ambil ID Pesan Ini
                msg_div = msg_wrap.find('div', class_='tgme_widget_message')
                if not msg_div: continue
                
                post_info = msg_div.get('data-post') # format: channelname/123
                current_msg_id = extract_message_id(post_info)
                
                if not current_msg_id: continue

                # 2. Ambil ID Pesan yang Di-Reply (Jika ada)
                reply_div = msg_wrap.find('a', class_='tgme_widget_message_reply')
                reply_to_id = None
                if reply_div:
                    reply_href = reply_div.get('href') # format: https://t.me/channel/123
                    reply_to_id = extract_message_id(reply_href)

                # 3. Ambil Teks
                text_content = msg_wrap.get_text(separator=' ', strip=True)
                
                # --- LOGIKA DETEKSI ---
                is_match = False
                match_reason = ""

                # CEK A: Apakah mengandung Keyword?
                if search_keyword.lower() in text_content.lower():
                    is_match = True
                    match_reason = "Keyword Found"
                
                # CEK B: Apakah me-reply pesan yang sedang kita pantau?
                # (Hanya jika kita punya tracked_msg_id sebelumnya)
                elif tracked_msg_id and reply_to_id == tracked_msg_id:
                    is_match = True
                    match_reason = "Reply Chain Detected"

                # EKSEKUSI JIKA MATCH
                if is_match:
                    # Cek Anti-Spam (Bandingkan snippet)
                    # Kita pakai snippet text sbg secondary check, utama pakai ID
                    if text_content != last_saved_snippet and current_msg_id != tracked_msg_id:
                        
                        print(f"--> UPDATE! {project_name} via {match_reason}")

                        alert_msg = (
                            f"🚨 **UPDATE DETECTED!** 🚨\n\n"
                            f"💎 **Project:** {project_name}\n"
                            f"🔗 **Reason:** {match_reason}\n"
                            f"📢 **Source:** @{source_channel}\n\n"
                            f"📜 **Isi Pesan:**\n{text_content[:300]}...\n\n"
                            f"[Buka Pesan](https://t.me/{source_channel}/{current_msg_id})"
                        )
                        
                        send_telegram_alert(alert_msg)
                        
                        # UPDATE DATABASE
                        # Penting: Kita simpan ID pesan INI sebagai tracked_id baru
                        # Jadi kalau nanti ada yang reply pesan INI, akan terdeteksi lagi (Estafet)
                        doc.reference.update({
                            'last_message_snippet': text_content,
                            'tracked_msg_id': current_msg_id
                        })
                        
                        # Update variabel lokal loop agar tidak trigger double di loop yang sama
                        tracked_msg_id = current_msg_id
                        last_saved_snippet = text_content

        except Exception as e:
            print(f"Error pada {project_name}: {e}")

if __name__ == "__main__":
    check_updates()
