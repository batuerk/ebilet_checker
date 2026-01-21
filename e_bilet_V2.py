import requests
import json
from datetime import datetime, timedelta
import threading
import locale
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from dotenv import load_dotenv
import os

# --- LOKAL AYARI (TÜRKÇE TARİHLER İÇİN) ---
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'tr_TR')
    except locale.Error:
        print("Turkish locale (tr_TR) bulunamadı, varsayılan locale kullanılıyor.")

load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

monitor_jobs = {}

# Dinamik istasyon verisi (global değişken)
STATIONS_DATA = []
STATIONS_BY_ID = {}

# Arama sonuçları depolaması
search_results = {}  # {chat_id: {"query": "", "results": [], "action": ""}}

params = {
    'environment': 'dev',
    'userId': '1',
}

def send_telegram_message(message: str, chat_id: str):
    """Telegram mesajı gönderir"""
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 400:
            print(f"HTML formatı hatası, düz metin olarak tekrar deneniyor...")
            payload.pop('parse_mode')
            retry_response = requests.post(url, data=payload, timeout=10)
            if retry_response.status_code == 200:
                print(f"Telegram mesajı (Düz Metin) {chat_id} için gönderildi.")
            else:
                print(f"Mesaj kurtarılamadı: {retry_response.text}")
        elif response.status_code == 200:
            print(f"Telegram mesajı {chat_id} için gönderildi.")
        else:
            print(f"Telegram mesajı gönderilemedi: {response.text}")
    except Exception as e:
        print(f"Telegram mesajı gönderme hatası: {e}")

def get_dynamic_token():
    """TCDD sitesinden dinamik token alır"""
    base_url = "https://ebilet.tcddtasimacilik.gov.tr"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    
    try:
        print(f"Ana sayfa ({base_url}) alınıyor...")
        main_page_response = requests.get(base_url, headers=headers, timeout=10)
        main_page_response.raise_for_status()
        
        html_content = main_page_response.text
        js_match = re.search(r'src="(/js/index\.[a-f0-9]+\.js\?.*?)"', html_content)
        if not js_match:
            print("HATA: Ana JS dosyası HTML'de bulunamadı.")
            return None
        
        js_file_url = base_url + js_match.group(1)
        print(f"Bulunan JS dosyası: {js_file_url}")
        
        js_response = requests.get(js_file_url, headers=headers, timeout=10)
        js_response.raise_for_status()
        
        js_content = js_response.text
        token_match = re.search(
            r'case\s*"TCDD-PROD":.*?["\'](eyJh[a-zA-Z0-9\._-]+)["\']', 
            js_content, 
            re.DOTALL
        )
        
        if not token_match:
            print("HATA: 'TCDD-PROD' token'ı bulunamadı.")
            return None
            
        access_token = token_match.group(1)
        print("✅ Dinamik token başarıyla bulundu.")
        return f"Bearer {access_token}"

    except Exception as e:
        print(f"HATA: Token alma hatası: {e}")
        return None

def load_stations():
    """İstasyonları TCDD API'sinden çeker ve global değişkene kaydeder"""
    global STATIONS_DATA, STATIONS_BY_ID
    
    dynamic_token = get_dynamic_token()
    if not dynamic_token:
        print("❌ Token alınamadı, istasyonlar yüklenemedi!")
        return False
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'tr',
        'Authorization': dynamic_token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://ebilet.tcddtasimacilik.gov.tr/',
        'unit-id': '3895',
    }
    
    url = 'https://cdn-api-prod-ytp.tcddtasimacilik.gov.tr/datas/station-pairs-INTERNET.json'
    
    try:
        print("🚂 İstasyonlar yükleniyor...")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ İstasyon listesi alınamadı. Durum: {response.status_code}")
            return False
        
        STATIONS_DATA = response.json()
        
        # ID bazlı hızlı erişim için dictionary oluştur
        for station in STATIONS_DATA:
            STATIONS_BY_ID[station['id']] = station
        
        print(f"✅ {len(STATIONS_DATA)} istasyon başarıyla yüklendi!")
        return True
        
    except Exception as e:
        print(f"❌ İstasyon yükleme hatası: {e}")
        return False

def get_station_by_id(station_id: int):
    """ID'ye göre istasyon bilgisini döndürür"""
    return STATIONS_BY_ID.get(station_id)

def get_available_destinations(from_station_id: int):
    """Belirli bir istasyondan gidilebilecek hedef istasyonları döndürür"""
    from_station = get_station_by_id(from_station_id)
    if not from_station or not from_station.get('pairs'):
        return []
    
    destinations = []
    for dest_id in from_station['pairs']:
        dest_station = get_station_by_id(dest_id)
        if dest_station and dest_station.get('ticketSaleActive'):
            destinations.append(dest_station)
    
    # İsme göre sırala
    destinations.sort(key=lambda x: x['name'])
    return destinations

def get_active_stations():
    """Bilet satışı aktif olan tüm istasyonları döndürür"""
    active_stations = [
        station for station in STATIONS_DATA 
        if station.get('ticketSaleActive') and station.get('pairs')
    ]
    # İsme göre sırala
    active_stations.sort(key=lambda x: x['name'])
    return active_stations

def search_stations(query: str, from_station_id: int = None):
    """Verilen sorguya göre istasyonları arar"""
    query_lower = query.lower().strip()
    
    if from_station_id:
        # Varış istasyonları ara
        stations = get_available_destinations(from_station_id)
    else:
        # Kalkış istasyonları ara
        stations = get_active_stations()
    
    # İsim veya şehir koduna göre ara
    filtered = [
        station for station in stations
        if query_lower in station['name'].lower() or 
           query_lower in station.get('city', {}).get('name', '').lower()
    ]
    
    return filtered

def check_api_and_parse(from_id: int, to_id: int, target_date: datetime):
    """API'yi kontrol eder ve bilet durumunu parse eder"""
    dynamic_token = get_dynamic_token()

    if not dynamic_token:
        return (False, "❌ HATA: Dinamik Authorization Token'ı alınamadı.")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'tr',
        'Authorization': dynamic_token,
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://ebilet.tcddtasimacilik.gov.tr',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'unit-id': '3895',
    }

    from_station = get_station_by_id(from_id)
    to_station = get_station_by_id(to_id)
    
    if not from_station or not to_station:
        return (False, "❌ HATA: İstasyon bilgisi bulunamadı.")

    api_search_date = target_date - timedelta(days=1)
    date_str = api_search_date.strftime("%d-%m-%Y") + " 21:00:00"

    json_data = {
        'searchRoutes': [
            {
                'departureStationId': from_id,
                'departureStationName': from_station['name'],
                'arrivalStationId': to_id,
                'arrivalStationName': to_station['name'],
                'departureDate': date_str,
            },
        ],
        'passengerTypeCounts': [{'id': 0, 'count': 1}],
        'searchReservation': False,
        'searchType': 'DOMESTIC',
        'blTrainTypes': ['TURISTIK_TREN'],
    }

    try:
        response = requests.post(
            'https://web-api-prod-ytp.tcddtasimacilik.gov.tr/tms/train/train-availability',
            params=params,
            headers=headers,
            json=json_data,
            timeout=15
        )

        if response.status_code == 401:
            return (False, "❌ HATA: API Token'ı geçersiz.")
        elif response.status_code != 200:
            return (False, f"❌ HATA: API yanıtı beklenmedik. Durum: {response.status_code}")

        data = response.json()
        sefer_gruplari_listesi = data["trainLegs"][0]["trainAvailabilities"]
        
        date_tr_str = target_date.strftime("%d %B %Y")
        route_str = f"<b>{from_station['name']} ➡ {to_station['name']}</b> | <b>{date_tr_str}</b>"

        if not sefer_gruplari_listesi:
            return (False, f"ℹ️ {route_str} yönüne uygun sefer bulunamadı.")

        result_message = f"✅ <b>{route_str}</b>\n\nBulunan seferler:\n"
        
        toplam_tren_sayaci = 0
        bulunan_koltuk = False
        
        for sefer_grubu in sefer_gruplari_listesi:
            trenler_listesi = sefer_grubu.get("trains")
            if not trenler_listesi:
                continue
                
            for tren in trenler_listesi:
                toplam_tren_sayaci += 1
                tren_mesaj_taslagi = ""
                vagon_bulundu_bu_trende = False
                
                try:
                    timestamp_ms = tren["segments"][0]["departureTime"]
                    timestamp_sn = timestamp_ms / 1000
                    kalkis_saati_str = datetime.fromtimestamp(timestamp_sn).strftime("%H:%M")
                    tren_adi = tren.get("trainName", f"Tren {toplam_tren_sayaci}")
                    
                    tren_mesaj_taslagi += f"\n<b>{tren_adi} (Kalkış: {kalkis_saati_str})</b>:\n"
                    
                    vagon_bilgisi_sozlugu = tren["availableFareInfo"][0]
                    vagon_siniflari_listesi = vagon_bilgisi_sozlugu["cabinClasses"]
                    
                    if not vagon_siniflari_listesi:
                        continue

                    for vagon in vagon_siniflari_listesi:
                        sinif_adi = vagon["cabinClass"]["name"]
                        uygun_koltuk = vagon["availabilityCount"]
                        
                        unwanted_types = ["TEKERLEKLİ SANDALYE", "YATAKLI", "LOCA"]
                        if sinif_adi.upper() in unwanted_types:
                            continue
                            
                        if uygun_koltuk > 0:
                            bulunan_koltuk = True
                            vagon_bulundu_bu_trende = True
                            minimum_fiyat = vagon["minPrice"]
                            tren_mesaj_taslagi += f"   ✅ <b>{sinif_adi}: {uygun_koltuk} adet</b> (min {minimum_fiyat} TRY)\n"

                    if vagon_bulundu_bu_trende:
                         result_message += tren_mesaj_taslagi
                         
                except (KeyError, IndexError, TypeError) as e:
                    print(f"Parsing error: {e}")

        if not bulunan_koltuk:
            return (False, f"ℹ️ {route_str} yönüne sefer bulundu, ancak <b>tüm vagonlar dolu</b>.")
        else:
            return (True, result_message)

    except Exception as e:
        return (False, f"❌ HATA: {e}")

def run_one_time_check(chat_id: str, from_id: int, to_id: int, target_date: datetime):
    """Tek seferlik kontrol"""
    from_station = get_station_by_id(from_id)
    to_station = get_station_by_id(to_id)
    
    print(f"Tek seferlik kontrol: {chat_id} | {from_station['name']} -> {to_station['name']}")
    
    found, message = check_api_and_parse(from_id, to_id, target_date)
    send_telegram_message(message, chat_id)
    print(f"Tek seferlik kontrol tamamlandı ({chat_id}).")

def monitoring_loop(chat_id: str, stop_event: threading.Event, from_id: int, to_id: int, target_date: datetime, interval_seconds: int):
    """Sürekli izleme döngüsü"""
    from_station = get_station_by_id(from_id)
    to_station = get_station_by_id(to_id)
    
    print(f"API İzleme başladı: {chat_id} | {from_station['name']} -> {to_station['name']}")
    send_telegram_message(
        f"Takip başladı: *{from_station['name']} ➡ {to_station['name']}* | {target_date.strftime('%d %B')}. "
        f"{interval_seconds} saniyede bir kontrol edilecek.",
        chat_id
    )
    
    previous_state = {}
    first_check = True
    
    while not stop_event.is_set():
        print(f"API Kontrol ediliyor ({chat_id})...")
        
        found, message = check_api_and_parse(from_id, to_id, target_date)
        
        current_state = {}
        
        if found:
            lines = message.split('\n')
            current_train = None
            current_train_total = 0
            
            for line in lines:
                if line.strip().startswith('<b>') and 'Kalkış:' in line:
                    if current_train:
                        current_state[current_train] = current_train_total
                    
                    train_info = line.split('(Kalkış:')[0].strip()
                    train_info = train_info.replace('<b>', '').replace('</b>', '')
                    current_train = train_info
                    current_train_total = 0
                
                elif '✅' in line and 'adet' in line:
                    try:
                        seat_count = int(line.split(':')[1].split('adet')[0].strip())
                        current_train_total += seat_count
                    except:
                        pass
            
            if current_train:
                current_state[current_train] = current_train_total
        
        if first_check:
            if found:
                print(f"İLK KONTROL - BOŞ YER BULUNDU! ({chat_id})")
                send_telegram_message("🎫 İLK KONTROL - BİLET DURUMU:\n\n" + message, chat_id)
                previous_state = current_state.copy()
            else:
                print(f"İLK KONTROL - BOŞ YER YOK ({chat_id})")
                send_telegram_message("ℹ️ İlk kontrol tamamlandı. Şu anda uygun yer bulunmuyor. Yer açıldığında bildirim alacaksınız.", chat_id)
            first_check = False
        
        else:
            if found:
                changes_detected = False
                change_message = "🚨 YENİ YER AÇILDI! 🚨\n\n"
                
                for train_name, current_seats in current_state.items():
                    previous_seats = previous_state.get(train_name, 0)
                    
                    if current_seats > previous_seats:
                        changes_detected = True
                        if previous_seats == 0:
                            change_message += f"🆕 <b>{train_name}</b>: YENİ SEFER - {current_seats} koltuk bulundu!\n"
                        else:
                            change_message += f"📈 <b>{train_name}</b>: {previous_seats} → {current_seats} koltuk (+{current_seats - previous_seats})\n"
                
                if changes_detected:
                    print(f"DEĞİŞİKLİK TESPİT EDİLDİ! ({chat_id})")
                    change_message += "\n" + message
                    send_telegram_message(change_message, chat_id)
                    previous_state = current_state.copy()
                else:
                    print(f"Değişiklik yok, mesaj atılmadı ({chat_id})")
            
            elif previous_state:
                print(f"TÜM YERLER DOLDU! ({chat_id})")
                send_telegram_message("❌ Daha önce uygun olan yerler doldu. Yeni yer açılmasını bekliyorum...", chat_id)
                previous_state = {}
        
        print(f"{interval_seconds} saniye bekleniyor...")
        if stop_event.wait(interval_seconds):
            break
            
    print(f"API İzleme durdu ({chat_id}).")
    if chat_id in monitor_jobs:
        del monitor_jobs[chat_id]
        print(f"İzleme işi listeden kaldırıldı ({chat_id}).")

def create_station_keyboard(action: str, from_station_id: int = None, search_query: str = None) -> InlineKeyboardMarkup:
    """Dinamik istasyon klavyesi oluşturur"""
    keyboard = []
    row = []
    
    if search_query:
        # Arama sonuçlarını göster
        stations = search_stations(search_query, from_station_id)
    elif from_station_id:
        # Varış istasyonları
        stations = get_available_destinations(from_station_id)
        prefix = f"to_{action}"
    else:
        # Kalkış istasyonları
        stations = get_active_stations()
        prefix = f"from_{action}"
    
    # Eğer arama sorgusu varsa, ona özel prefix kullan
    if search_query:
        if from_station_id:
            prefix = f"search_to_{action}_{from_station_id}"  # from_station_id dahil
        else:
            prefix = f"search_from_{action}"
    
    for station in stations[:20]:  # Maksimum 20 sonuç göster
        station_name = station['name'][:25]  # Uzun isimleri kısalt
        callback_data = f"{prefix}_{station['id']}"
        
        row.append(InlineKeyboardButton(station_name, callback_data=callback_data))
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # Arama butonu ekle (hem kalkış hem varış için)
    if search_query:
        keyboard.append([InlineKeyboardButton("🔍 Yeni Arama", callback_data=f"newsearch_{'to' if from_station_id else 'from'}_{action}_{from_station_id if from_station_id else '0'}")])
    elif from_station_id:
        # Varış istasyonu seçimi - arama butonu ekle
        keyboard.append([InlineKeyboardButton("🔍 Varış İstasyonu Ara", callback_data=f"search_input_to_{action}_{from_station_id}")])
    else:
        # Kalkış istasyonu seçimi - arama butonu ekle
        keyboard.append([InlineKeyboardButton("🔍 Kalkış İstasyonu Ara", callback_data=f"search_input_from_{action}")])
    
    if not stations and search_query:
        keyboard = [[InlineKeyboardButton("❌ Sonuç bulunamadı", callback_data="error")],
                    [InlineKeyboardButton("🔍 Yeni Arama", callback_data=f"newsearch_{'to' if from_station_id else 'from'}_{action}_{from_station_id if from_station_id else '0'}")]]
    elif not keyboard:
        keyboard.append([InlineKeyboardButton("İstasyon bulunamadı", callback_data="error")])
        
    return InlineKeyboardMarkup(keyboard)

def create_date_keyboard(action: str, from_station_id: int, to_station_id: int) -> InlineKeyboardMarkup:
    """Tarih seçim klavyesi"""
    keyboard = []
    today = datetime.today()
    
    row = []
    for i in range(0, 13):
        day = today + timedelta(days=i)
        date_str_iso = day.strftime("%Y-%m-%d")
        
        callback_data = f"date_{action}_{from_station_id}_{to_station_id}_{date_str_iso}"
        
        if i == 0:
            day_name = "Bugün"
        elif i == 1:
            day_name = "Yarın"
        else:
            day_name = day.strftime("%A")
        
        button_text = f"{day_name.capitalize()} ({day.strftime('%d %b').capitalize()})"
        row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row: 
        keyboard.append(row)
        
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext):
    """/start komutu"""
    message = """
👋 Merhaba! Ben TCDD API Bilet Takip Botuyum.

*KOMUTLAR:*
• `/check` - Tek seferlik bilet kontrolü
• `/monitor` - Sürekli bilet takibi
• `/stop` - Aktif izlemeyi durdurur

İstasyonlar TCDD'den dinamik olarak yüklenir.
    """
    await update.message.reply_text(message, parse_mode='Markdown')

async def check_command(update: Update, context: CallbackContext):
    """/check komutu"""
    if not STATIONS_DATA:
        await update.message.reply_text("⏳ İstasyonlar yükleniyor, lütfen bekleyin...")
        if not load_stations():
            await update.message.reply_text("❌ İstasyonlar yüklenemedi. Lütfen daha sonra tekrar deneyin.")
            return
    
    context.user_data['action'] = 'check'
    context.user_data['from_station_id'] = None
    
    keyboard = create_station_keyboard(action="check")
    await update.message.reply_text(
        "Lütfen *kalkış* istasyonunu seçin veya 🔍 ile arayın:", 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def monitor_command(update: Update, context: CallbackContext):
    """/monitor komutu"""
    chat_id = str(update.message.chat_id)
    if chat_id in monitor_jobs:
        await update.message.reply_text("Zaten aktif bir izlemeniz var. Durdurmak için /stop yazın.")
        return
    
    if not STATIONS_DATA:
        await update.message.reply_text("⏳ İstasyonlar yükleniyor, lütfen bekleyin...")
        if not load_stations():
            await update.message.reply_text("❌ İstasyonlar yüklenemedi. Lütfen daha sonra tekrar deneyin.")
            return
    
    context.user_data['action'] = 'monitor'
    context.user_data['from_station_id'] = None
    
    keyboard = create_station_keyboard(action="monitor")
    await update.message.reply_text(
        "Lütfen *kalkış* istasyonunu seçin veya 🔍 ile arayın:", 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def stop_command(update: Update, context: CallbackContext):
    """/stop komutu"""
    chat_id = str(update.message.chat_id)
    
    if chat_id in monitor_jobs:
        monitor_thread, stop_event = monitor_jobs.pop(chat_id)
        print(f"Durdurma sinyali gönderiliyor: {chat_id}")
        stop_event.set()
        await update.message.reply_text("İzleme durduruluyor... 🛑")
    else:
        await update.message.reply_text("Aktif bir izlemeniz bulunmuyor.")

async def search_input_handler(update: Update, context: CallbackContext):
    """Arama sorgusu için metin girişini işler"""
    chat_id = str(update.message.chat_id)
    query = update.message.text.strip()
    
    print(f"[DEBUG] Metin alındı: '{query}' | user_data: {context.user_data}")
    
    # Sadece arama bekliyorsak işle
    if not context.user_data.get('waiting_for_search'):
        print(f"[DEBUG] Arama beklenmiyordu, mesaj yok sayıldı")
        return
    
    if not query or len(query) < 2:
        await update.message.reply_text("Lütfen en az 2 karakter girin.")
        return
    
    # Arama sonuçlarını bul
    if 'action' in context.user_data:
        action = context.user_data['action']
        from_station_id = context.user_data.get('from_station_id')
        
        # Arama tamamlandı, flag'i sıfırla
        context.user_data['waiting_for_search'] = False
        
        results = search_stations(query, from_station_id)
        
        if results:
            keyboard = create_station_keyboard(
                action=action,
                from_station_id=from_station_id,
                search_query=query
            )
            
            header = f"*{len(results)} sonuç bulundu:*\n\n"
            if from_station_id:
                from_station = get_station_by_id(from_station_id)
                header = f"Kalkış: *{from_station['name']}*\n\n*{len(results)} varış istasyonu bulundu:*\n\n"
            
            await update.message.reply_text(
                header + "\n".join([f"• {s['name']}" for s in results[:10]]),
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ '*{query}*' için sonuç bulunamadı. Lütfen başka bir ad deneyin.", parse_mode='Markdown')
            # Arama butonu için doğru callback_data oluştur
            if from_station_id:
                search_callback = f"search_input_to_{action}_{from_station_id}"
            else:
                search_callback = f"search_input_from_{action}"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 Tekrar Ara", callback_data=search_callback)]
            ])
            await update.message.reply_text("Arama yapmak ister misiniz?", reply_markup=keyboard)
    else:
        await update.message.reply_text("Seçim konteksti kaybedildi. Lütfen /check veya /monitor komutundan başlayın.")

async def button_callback(update: Update, context: CallbackContext):
    """Inline button callback handler"""
    query = update.callback_query
    await query.answer()
    
    chat_id = str(query.message.chat_id)
    
    try:
        parts = query.data.split('_')
        prefix = parts[0]

        # Arama girişi (kalkış veya varış için)
        if query.data.startswith('search_input_'):
            parts_search = query.data.split('_')
            search_type = parts_search[2]  # 'from' veya 'to'
            action = parts_search[3]
            
            context.user_data['action'] = action
            context.user_data['search_type'] = search_type
            context.user_data['waiting_for_search'] = True  # Arama bekliyoruz
            print(f"[DEBUG] Arama modu aktif: action={action}, search_type={search_type}")
            
            if search_type == 'to' and len(parts_search) > 4:
                from_station_id = int(parts_search[4])
                context.user_data['from_station_id'] = from_station_id
                from_station = get_station_by_id(from_station_id)
                await query.message.reply_text(
                    f"Kalkış: *{from_station['name']}*\n\n"
                    "Lütfen varış istasyonu aramak için istasyon adı yazın (en az 2 karakter):\n\n"
                    "Örnek: İstanbul, Ankara, Konya vb.",
                    parse_mode='Markdown'
                )
            else:
                context.user_data['from_station_id'] = None
                await query.message.reply_text(
                    "Lütfen kalkış istasyonu aramak için istasyon adı yazın (en az 2 karakter):\n\n"
                    "Örnek: İstanbul, Ankara, Konya vb."
                )
            return

        # Yeni arama
        if prefix == 'newsearch':
            station_type = parts[1]
            action = parts[2]
            from_station_id = int(parts[3]) if len(parts) > 3 and parts[3] and parts[3] != '0' else None
            
            context.user_data['action'] = action
            context.user_data['from_station_id'] = from_station_id
            context.user_data['waiting_for_search'] = True  # Arama bekliyoruz
            print(f"[DEBUG] Yeni arama modu aktif: action={action}, from_station_id={from_station_id}")
            
            if from_station_id:
                from_station = get_station_by_id(from_station_id)
                await query.message.reply_text(
                    f"Kalkış: *{from_station['name']}*\n\n"
                    "Lütfen varış istasyonu aramak için istasyon adı yazın (en az 2 karakter):\n\n"
                    "Örnek: İstanbul, Ankara, Konya vb.",
                    parse_mode='Markdown'
                )
            else:
                await query.message.reply_text(
                    "Lütfen kalkış istasyonu aramak için istasyon adı yazın (en az 2 karakter):\n\n"
                    "Örnek: İstanbul, Ankara, Konya vb."
                )
            return

        # Arama sonuçlarından seçim
        # Format: search_from_{action}_{station_id} veya search_to_{action}_{from_station_id}_{to_station_id}
        if prefix == 'search':
            station_type = parts[1]  # 'from' veya 'to'
            action = parts[2]
            
            if station_type == 'from':
                # Kalkış istasyonu seçildi: search_from_{action}_{station_id}
                station_id = int(parts[3])
                from_station = get_station_by_id(station_id)
                context.user_data['from_station_id'] = station_id
                
                keyboard = create_station_keyboard(action=action, from_station_id=station_id)
                await query.edit_message_text(
                    text=f"Kalkış: *{from_station['name']}*\n\nŞimdi *varış* istasyonunu seçin:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            elif station_type == 'to':
                # Varış istasyonu seçildi: search_to_{action}_{from_station_id}_{to_station_id}
                from_station_id = int(parts[3])
                to_station_id = int(parts[4])
                
                from_station = get_station_by_id(from_station_id)
                to_station = get_station_by_id(to_station_id)
                
                keyboard = create_date_keyboard(action=action, from_station_id=from_station_id, to_station_id=to_station_id)
                await query.edit_message_text(
                    text=f"Kalkış: *{from_station['name']}*\nVarış: *{to_station['name']}*\n\nLütfen bir *tarih* seçin:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            return

        if prefix == 'from':
            action = parts[1]
            from_station_id = int(parts[2])
            from_station = get_station_by_id(from_station_id)
            context.user_data['from_station_id'] = from_station_id
            
            keyboard = create_station_keyboard(action=action, from_station_id=from_station_id)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station['name']}*\n\nŞimdi *varış* istasyonunu seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        elif prefix == 'to':
            action = parts[1]
            from_station_id = int(parts[2])
            to_station_id = int(parts[3])
            
            from_station = get_station_by_id(from_station_id)
            to_station = get_station_by_id(to_station_id)
            
            keyboard = create_date_keyboard(action=action, from_station=from_station_id, to_station=to_station_id)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station['name']}*\nVarış: *{to_station['name']}*\n\nLütfen bir *tarih* seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        elif prefix == 'date':
            action = parts[1]
            from_station_id = int(parts[2])
            to_station_id = int(parts[3])
            date_iso_str = parts[4]
            target_date = datetime.strptime(date_iso_str, "%Y-%m-%d")
            
            from_station = get_station_by_id(from_station_id)
            to_station = get_station_by_id(to_station_id)
            
            date_tr_str = target_date.strftime("%d %B %Y")
            await query.edit_message_text(
                text=f"🚆 *{from_station['name']}* ➡ *{to_station['name']}*\n🗓 *{date_tr_str}*\n\nAPI sorgulanıyor...", 
                parse_mode='Markdown'
            )

            if action == "check":
                print(f"Check başlatıldı: {from_station['name']} -> {to_station['name']}")
                threading.Thread(
                    target=run_one_time_check,
                    args=(chat_id, from_station_id, to_station_id, target_date)
                ).start()
            
            elif action == "monitor":
                if chat_id in monitor_jobs:
                    await query.message.reply_text("Zaten aktif bir izlemeniz var. /stop")
                    return

                print(f"Monitor başlatıldı: {from_station['name']} -> {to_station['name']}")
                check_interval = 30
                stop_event = threading.Event()
                monitor_thread = threading.Thread(
                    target=monitoring_loop,
                    args=(chat_id, stop_event, from_station_id, to_station_id, target_date, check_interval)
                )
                
                monitor_jobs[chat_id] = (monitor_thread, stop_event)
                monitor_thread.start()

    except Exception as e:
        print(f"Callback hatası: {e}")
        await query.message.reply_text(f"Buton işlemi sırasında hata: {e}")

def main():
    """Bot başlatma"""
    print("🚂 TCDD Bilet Takip Botu başlatılıyor...")
    
    # İstasyonları ilk başta yükle
    if not load_stations():
        print("⚠️ İstasyonlar yüklenemedi, bot yine de başlatılıyor...")
    
    builder = Application.builder().token(TELEGRAM_API_TOKEN)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("monitor", monitor_command))
    app.add_handler(CommandHandler("stop", stop_command))
    
    app.add_handler(CallbackQueryHandler(button_callback, pattern='^(from_|to_|date_|search|newsearch)'))
    
    # Metin mesajları işle (arama sorguları için)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_input_handler))

    print("✅ Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
