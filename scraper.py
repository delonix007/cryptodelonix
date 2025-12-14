import os
import requests
import re
import firebase_admin
from bs4 import BeautifulSoup
from firebase_admin import credentials, firestore

# ... (Bagian Konfigurasi & Init Firebase sama seperti sebelumnya) ...

def check_updates():
    print("--- MULAI HYBRID SCRAPING ---")
    
    # Ambil data Active
    docs = db.collection('airdrops').where('status', '==', 'Active').stream()

    for doc in docs:
        data = doc.to_dict()
        project_name = data.get('name')
        source_channel = data.get('source')
        
        # Ambil Keyword & ID
        search_keyword = data.get('search_keyword', '').lower()
        tracked_msg_id = str(data.get('tracked_msg_id', '')) # Pastikan string
        
        print(f"\n🔍 Tracking: {project_name} | Key: {search_keyword} | ID: {tracked_msg_id}")
        
        url = f"https://t.me/s/{source_channel}"
        
        try:
            r = requests.get(url, timeout=20)
            soup = BeautifulSoup(r.text, 'html.parser')
            
            # Ambil 15 pesan terakhir
            messages = soup.find_all('div', class_='tgme_widget_message_wrap')
            
            # Loop dari pesan terlama ke terbaru (agar alur update runtut)
            for msg_wrap in messages:
                msg_div = msg_wrap.find('div', class_='tgme_widget_message')
                if not msg_div: continue
                
                # 1. Dapatkan ID Pesan Ini
                post_link = msg_div.get('data-post') 
                current_msg_id = extract_id_from_url(post_link)
                if not current_msg_id: continue

                # Skip jika pesan ini <= pesan yang terakhir kita simpan (sudah lama)
                # (Logic sederhana: anggap ID makin besar makin baru)
                if tracked_msg_id and current_msg_id.isdigit() and tracked_msg_id.isdigit():
                    if int(current_msg_id) <= int(tracked_msg_id):
                        continue 

                # 2. Dapatkan Text & Reply ID
                text_div = msg_wrap.find('div', class_='tgme_widget_message_text')
                raw_text = text_div.get_text(separator=' ', strip=True) if text_div else ""
                text_lower = raw_text.lower()
                
                reply_div = msg_wrap.find('a', class_='tgme_widget_message_reply')
                reply_to_id = extract_id_from_url(reply_div.get('href')) if reply_div else None

                # --- INI LOGIKA HYBRID-NYA ---
                match_found = False
                match_reason = ""

                # CEK 1: Apakah dia Reply ke ID yang kita pantau? (Akurasi Tinggi)
                if tracked_msg_id and reply_to_id == tracked_msg_id:
                    match_found = True
                    match_reason = "Reply ke Thread Utama"

                # CEK 2: Apakah dia mengandung Keyword? (Backup Plan)
                # Dijalankan jika Admin membuat post baru (bukan reply)
                elif search_keyword and search_keyword in text_lower:
                    match_found = True
                    match_reason = f"Keyword '{search_keyword}' ditemukan"

                # --- EKSEKUSI ---
                if match_found:
                    print(f"   ✅ UPDATE BARU! ID: {current_msg_id} ({match_reason})")
                    
                    # 1. Kirim Telegram
                    msg = (
                        f"🚨 **UPDATE: {project_name}**\n"
                        f"Info: {match_reason}\n\n"
                        f"_{raw_text[:300]}..._\n\n"
                        f"[Buka Pesan](https://t.me/{source_channel}/{current_msg_id})"
                    )
                    send_telegram_alert(msg)

                    # 2. AUTO-SWITCH ID (PENTING!)
                    # Kita update 'tracked_msg_id' di database ke ID pesan BARU ini.
                    # Jadi jika nanti admin me-reply pesan baru ini, kita tetap bisa detect.
                    doc.reference.update({
                        'tracked_msg_id': current_msg_id,
                        'last_message_snippet': raw_text[:50]
                    })
                    
                    # Update variabel lokal agar loop selanjutnya membandingkan dengan ID baru ini
                    tracked_msg_id = current_msg_id

        except Exception as e:
            print(f"Error: {e}")

# ... (Fungsi helper lainnya sama)
