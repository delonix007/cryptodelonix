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

# Inisialisasi Firebase
if not firebase_admin._apps:
    if os.path.exists("firebase_key.json"):
        cred = credentials.Certificate("firebase_key.json") 
        firebase_admin.initialize_app(cred)
    else:
        print("Mencoba inisialisasi tanpa file JSON (Environment)...")
        # Jika pakai cara ENV variable langsung di GitHub Actions (opsional)
        # Jika tidak, pastikan step 'Create Firebase Key File' di YAML berjalan sukses

db = firestore.client()

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # disable_web_page_preview=True agar chat tidak penuh gambar
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
    print("--- MULAI SCRAPING ---")
    
    try:
        # Ambil data yang statusnya Active
        docs = db.collection('airdrops').where('status', '==', 'Active').stream()
    except Exception as e:
        print(f"Error Database: {e}")
        return

    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        source_channel = data.get('source')
        
        # Keyword & ID Terakhir
        search_keyword = data.get('search_keyword', project_name).lower() # Pakai huruf kecil
        tracked_msg_id = data.get('tracked_msg_id') 
        last_saved_snippet = data.get('last_message_snippet', '')

        print(f"\n🔍 Cek Project: {project_name} | Keyword: '{search_keyword}' | Tracked ID: {tracked_msg_id}")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            r = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Ambil 15 pesan terakhir (diperbanyak agar tidak kelewatan)
            messages = soup.find_all('div', class_='tgme_widget_message_wrap')
            
            if not messages: 
                print(f"   ⚠️ Tidak ada pesan ditemukan di @{source_channel}. Channel private/salah username?")
                continue

            # Loop pesan dari yang LAMA ke BARU (agar urutan update benar)
            # Pesan paling bawah di HTML adalah pesan paling baru.
            # Tapi di soup.find_all, urutannya dari atas (lama) ke bawah (baru).
            # Kita ambil 15 terakhir.
            recent_messages = messages[-15:]

            for msg_wrap in recent_messages:
                
                # 1. Ambil ID Pesan Ini
                msg_div = msg_wrap.find('div', class_='tgme_widget_message')
                if not msg_div: continue
                
                post_link = msg_div.get('data-post') # format: channel/123
                current_msg_id = extract_id_from_url(post_link)
                
                if not current_msg_id: continue

                # 2. Ambil Text (Bersihkan spasi)
                text_div = msg_wrap.find('div', class_='tgme_widget_message_text')
                raw_text = text_div.get_text(separator=' ', strip=True) if text_div else "[Media/Gambar]"
                text_lower = raw_text.lower()

                # 3. Cek Reply (Apakah pesan ini membalas pesan lain?)
                reply_div = msg_wrap.find('a', class_='tgme_widget_message_reply')
                reply_to_id = None
                if reply_div:
                    reply_href = reply_div.get('href')
                    reply_to_id = extract_id_from_url(reply_href)

                # --- LOGIKA DETEKSI "PRESEN" YANG HILANG ---
                is_match = False
                match_reason = ""

                # CEK A: Apakah mengandung Keyword? (PRIORITAS UTAMA)
                if search_keyword in text_lower:
                    is_match = True
                    match_reason = f"Keyword '{search_keyword}' ditemukan"
                
                # CEK B: Estafet ID (Jika pesan ini membalas ID yang kita pantau)
                # Syarat: tracked_msg_id harus ada datanya di database
                elif tracked_msg_id and reply_to_id == tracked_msg_id:
                    is_match = True
                    match_reason = f"Reply ke ID pantauan ({tracked_msg_id})"

                # --- EKSEKUSI JIKA MATCH ---
                if is_match:
                    # Cek Anti-Spam: Apakah pesan ini SAMA PERSIS dengan yang terakhir dikirim?
                    # Kita cek dari ID pesannya. Jika ID ini > Tracked ID (atau berbeda), kirim.
                    
                    # Logic sederhana: Jika ID pesan ini BEDA dengan yang disimpan di database
                    if str(current_msg_id) != str(tracked_msg_id):
                        
                        print(f"   ✅ UPDATE DITEMUKAN! ID: {current_msg_id} | Alasan: {match_reason}")

                        # Format Pesan Cantik
                        reply_info = f"(Reply to msg #{reply_to_id})" if reply_to_id else "(Direct Post)"
                        
                        alert_msg = (
                            f"🚨 **UPDATE GARAPAN: {project_name}**\n\n"
                            f"🔍 **Deteksi:** {match_reason}\n"
                            f"📡 **Source:** @{source_channel}\n"
                            f"🔗 **Info:** {reply_info}\n\n"
                            f"📜 **Isi Pesan:**\n_{raw_text[:300]}..._\n\n"
                            f"[👉 Buka Pesan di Telegram](https://t.me/{source_channel}/{current_msg_id})"
                        )
                        
                        send_telegram_alert(alert_msg)
                        
                        # UPDATE DATABASE
                        # Simpan ID pesan INI sebagai tracked_id baru.
                        # Sehingga jika ada yang reply pesan ini, akan terdeteksi lagi.
                        doc.reference.update({
                            'last_message_snippet': raw_text[:50], # Simpan potongan pendek saja
                            'tracked_msg_id': current_msg_id
                        })
                        
                        # Update variabel lokal loop agar tidak trigger berkali-kali di run yang sama
                        tracked_msg_id = current_msg_id
                    else:
                        pass
                        # print(f"   (Skip ID {current_msg_id}: Sudah pernah dikirim)")

        except Exception as e:
            print(f"   ❌ Error checking {project_name}: {e}")

    print("--- SELESAI SCRAPING ---")

if __name__ == "__main__":
    check_updates()
