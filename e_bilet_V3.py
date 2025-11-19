import requests
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
import threading
import locale
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler

# --- LOKAL AYARI (TÜRKÇE TARİHLER İÇİN) ---
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'tr_TR')
    except locale.Error:
        print("Turkish locale (tr_TR) bulunamadı, varsayılan locale kullanılıyor. Tarihler İngilizce görünebilir.")
# ---------------------------------------------

load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") 

monitor_jobs = {}

STATION_MAP = {
    "SÖĞÜTLÜÇEŞME": {'id': 1325, 'fullName': 'İSTANBUL(SÖĞÜTLÜÇEŞME)'},
    "ARİFİYE":       {'id': 5,    'fullName': 'ARİFİYE'},

    "SAPANCA":      {'id': 69, 'fullName': 'SAPANCA'}, 
    "İZMİT":        {'id': 1135, 'fullName': 'İZMİT'}, 
    "GEBZE":        {'id': 617, 'fullName': 'GEBZE'}, 
    "PENDİK":       {'id': 48, 'fullName': 'İSTANBUL(PENDİK)'}, 
    "BOSTANCI":     {'id': 1323, 'fullName': 'İSTANBUL(BOSTANCI)'}, 
    "BAKIRKÖY":     {'id': 1328, 'fullName': 'İSTANBUL(BAKIRKÖY)'}, 
    "HALKALI":      {'id': 992, 'fullName': 'İSTANBUL(HALKALI)'},
    "ERYAMAN":      {'id': 1306, 'fullName': 'ERYAMAN YHT'},
    "POLATLI":      {'id': 244, 'fullName': 'POLATLI YHT'},
    "SİNCAN":       {'id': 192, 'fullName': 'SİNCAN'},
    "ANKARA GAR":   {'id': 98, 'fullName': 'ANKARA GAR'},
}

params = {
    'environment': 'dev',
    'userId': '1',
}

def send_telegram_message(message: str, chat_id: str):
    """(Thread içinden mesaj göndermek için)"""
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            print(f"Telegram mesajı {chat_id} için gönderildi.")
        else:
            print(f"Telegram mesajı {chat_id} için gönderilemedi:", response.text)
    except Exception as e:
        print(f"Telegram mesajı {chat_id} için gönderme hatası:", e)

def get_dynamic_token():
    base_url = "https://ebilet.tcddtasimacilik.gov.tr"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    }
    
    try:
        print(f"Ana sayfa ({base_url}) alınıyor...")
        main_page_response = requests.get(base_url, headers=headers, timeout=10)
        main_page_response.raise_for_status()
        
        html_content = main_page_response.text
        
        js_match = re.search(r'src="(/js/index\.[a-f0-9]+\.js\?.*?)"', html_content)
        if not js_match:
            print("HATA: Ana JS dosyası (index...js) HTML'de bulunamadı.")
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
        print(token_match)
        
        if not token_match:
            print("HATA: 'TCDD-PROD' token'ı JS dosyası içinde bulunamadı. (RegEx başarısız)")
            return None
            
        access_token = token_match.group(1)
        print("Dinamik token başarıyla bulundu ve ayıklandı.")
        return f"Bearer {access_token}"

    except requests.exceptions.RequestException as e:
        print(f"HATA: Token alma işlemi sırasında ağ hatası: {e}")
        return None
    except Exception as e:
        print(f"HATA: Token ayrıştırılırken genel bir hata oluştu: {e}")
        return None

def check_api_and_parse(from_key: str, to_key: str, target_date: datetime):

    dynamic_token = get_dynamic_token()

    if not dynamic_token:
        return (False, "❌ HATA: Dinamik Authorization Token'ı alınamadı. Botun 'get_dynamic_token' fonksiyonunu kontrol edin.")

    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'tr',
        'Authorization': dynamic_token,
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://ebilet.tcddtasimacilik.gov.tr',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
        'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'unit-id': '3895',
    }

    from_station = STATION_MAP[from_key]
    to_station = STATION_MAP[to_key]

    api_search_date = target_date - timedelta(days=1)

    date_str = api_search_date.strftime("%d-%m-%Y") + " 21:00:00"

    json_data = {
        'searchRoutes': [
            {
                'departureStationId': from_station['id'],
                'departureStationName': from_station['fullName'],
                'arrivalStationId': to_station['id'],
                'arrivalStationName': to_station['fullName'],
                'departureDate': date_str,
            },
        ],
        'passengerTypeCounts': [
            {
                'id': 0,
                'count': 1,
            },
        ],
        'searchReservation': False,
        'searchType': 'DOMESTIC',
        'blTrainTypes': [
            'TURISTIK_TREN',
        ],
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
            return (False, "❌ HATA: API Yetki (Authorization) Token'ı geçersiz veya süresi dolmuş. Botun sahibinin `.env` dosyasında token'ı güncellemesi gerekiyor.")
        elif response.status_code != 200:
            return (False, f"❌ HATA: API'den beklenmedik bir yanıt alındı. Durum Kodu: {response.status_code}\nYanıt: {response.text[:100]}")

        data = response.json()
        
        sefer_gruplari_listesi = data["trainLegs"][0]["trainAvailabilities"]
        
        date_tr_str = target_date.strftime("%d %B %Y")
        route_str = f"*{from_key.capitalize()} ➡ {to_key.capitalize()}* | *{date_tr_str}*"

        if not sefer_gruplari_listesi:
            return (False, f"ℹ️ Maalesef, {route_str} yönüne uygun sefer bulunamadı.")

        result_message = f"✅ *{route_str}*\n\nBulunan seferler:\n"
        
        toplam_tren_sayaci = 0
        bulunan_koltuk = False
        
        for i, sefer_grubu in enumerate(sefer_gruplari_listesi):
            trenler_listesi = sefer_grubu.get("trains")
            if not trenler_listesi:
                continue
                
            for j, tren in enumerate(trenler_listesi):
                toplam_tren_sayaci += 1
                
                try:
                    timestamp_ms = tren["segments"][0]["departureTime"]
                    timestamp_sn = timestamp_ms / 1000
                    kalkis_saati_str = datetime.fromtimestamp(timestamp_sn).strftime("%H:%M")
                    tren_adi = tren.get("trainName", f"Tren {toplam_tren_sayaci}")
                    
                    result_message += f"\n*{tren_adi} (Kalkış: {kalkis_saati_str})*:\n"
                    
                    vagon_bilgisi_sozlugu = tren["availableFareInfo"][0]
                    vagon_siniflari_listesi = vagon_bilgisi_sozlugu["cabinClasses"]
                    
                    if not vagon_siniflari_listesi:
                        result_message += "   - (Vagon bilgisi bulunamadı)\n"
                        continue

                    vagon_bulundu_bu_trende = False

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
                            result_message += f"   ✅ *{sinif_adi}: {uygun_koltuk} adet* (min {minimum_fiyat} TRY)\n"
                        
                    if not vagon_bulundu_bu_trende:
                         result_message += "   - (Uygun vagonlar dolu)\n"
                         
                except (KeyError, IndexError, TypeError) as e:
                    print(f"Parsing error for one train: {e}")
                    result_message += "   - (Bu trenin verisi okunurken hata oluştu)\n"

        if not bulunan_koltuk:
            return (False, f"ℹ️ {route_str} yönüne sefer bulundu, ancak *tüm vagonlar dolu*.")
        else:
            return (True, result_message)

    except requests.exceptions.RequestException as e:
        return (False, f"❌ HATA: API'ye bağlanırken bir sorun oluştu: {e}")
    except (KeyError, IndexError, TypeError) as e:
        return (False, f"❌ HATA: API'den gelen yanıtın yapısı değişmiş. Yanıt ayrıştırılamadı. Hata: {e}")

def run_one_time_check(chat_id: str, from_key: str, to_key: str, target_date: datetime):

    print(f"Tek seferlik API kontrolü: {chat_id} | {from_key} -> {to_key} | {target_date.strftime('%d.%m.%Y')}")
    
    found, message = check_api_and_parse(from_key, to_key, target_date)
    
    send_telegram_message(message, chat_id)
    print(f"Tek seferlik kontrol tamamlandı ({chat_id}).")

def monitoring_loop(chat_id: str, stop_event: threading.Event, from_key: str, to_key: str, target_date: datetime, interval_seconds: int):

    print(f"API İzleme başladı: {chat_id} | {from_key} -> {to_key} | {target_date.strftime('%d.%m.%Y')}")
    send_telegram_message(
        f"Takip başladı: *{from_key.capitalize()} ➡ {to_key.capitalize()}* | {target_date.strftime('%d %B')}. "
        f"{interval_seconds} saniyede bir kontrol edilecek. Sadece boş yer bulunca haber vereceğim. 🤫",
        chat_id
    )
    
    while not stop_event.is_set():
        print(f"API Kontrol ediliyor ({chat_id})...")
        
        found, message = check_api_and_parse(from_key, to_key, target_date)
        
        if found:
            print(f"BOŞ YER BULUNDU! ({chat_id})")
            send_telegram_message("🚨 BİLET BULUNDU! 🚨\n\n" + message, chat_id)
            # İsteğe bağlı: Bulunca dursun
            # stop_event.set() 
            # break
        
        print(f"{interval_seconds} saniye bekleniyor...")
        if stop_event.wait(interval_seconds):
            break
            
    print(f"API İzleme durdu ({chat_id}).")
    if chat_id in monitor_jobs:
        del monitor_jobs[chat_id]
        print(f"İzleme işi listeden kaldırıldı ({chat_id}).")

def create_station_keyboard(action: str, from_station: str = None) -> InlineKeyboardMarkup:
    keyboard = []
    row = []
    
    if from_station:
        stations_to_show = [s for s in STATION_MAP.keys() if s != from_station]
        prefix = f"to_{action}_{from_station}"
    else:
        stations_to_show = list(STATION_MAP.keys())
        prefix = f"from_{action}"
        
    for station_key in stations_to_show:
        callback_data = f"{prefix}_{station_key}"
        row.append(InlineKeyboardButton(station_key.capitalize(), callback_data=callback_data))
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
        
    return InlineKeyboardMarkup(keyboard)

def create_date_keyboard(action: str, from_station: str, to_station: str) -> InlineKeyboardMarkup:
    keyboard = []
    today = datetime.today()
    
    row = []
    for i in range(0, 13):
        day = today + timedelta(days=i)
        date_str_iso = day.strftime("%Y-%m-%d")
        
        callback_data = f"date_{action}_{from_station}_{to_station}_{date_str_iso}"
        
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

Senin için istediğin seferleri *ışık hızında* kontrol edebilirim.

*KOMUTLAR:*
• `/check` - Tek seferlik bilet kontrolü için adımları başlatır.
• `/monitor` - Sürekli bilet takibi için adımları başlatır.
• `/stop` - Aktif izlemeyi durdurur.

Kalkış, varış ve tarih bilgilerini komutu verdikten sonra seçeceksin.
    """
    await update.message.reply_text(message, parse_mode='Markdown')

async def check_command(update: Update, context: CallbackContext):
    """/check komutu"""
    keyboard = create_station_keyboard(action="check")
    await update.message.reply_text(
        "Lütfen *kalkış* istasyonunu seçin:", 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def monitor_command(update: Update, context: CallbackContext):
    """/monitor komutu"""
    chat_id = str(update.message.chat_id)
    if chat_id in monitor_jobs:
        await update.message.reply_text("Zaten aktif bir izlemeniz bulunuyor. Durdurmak için /stop yazın.")
        return
    
    keyboard = create_station_keyboard(action="monitor")
    await update.message.reply_text(
        "Lütfen *kalkış* istasyonunu seçin:", 
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

async def button_callback(update: Update, context: CallbackContext):
    """Tüm inline butonlara basıldığında tetiklenir."""
    query = update.callback_query
    await query.answer()
    
    chat_id = str(query.message.chat_id)
    
    try:
        parts = query.data.split('_')
        prefix = parts[0]

        if prefix == 'from':
            action = parts[1]
            from_station_key = parts[2]
            
            keyboard = create_station_keyboard(action=action, from_station=from_station_key)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station_key.capitalize()}*\n\nŞimdi *varış* istasyonunu seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        elif prefix == 'to':
            action = parts[1]
            from_station_key = parts[2]
            to_station_key = parts[3]
            
            keyboard = create_date_keyboard(action=action, from_station=from_station_key, to_station=to_station_key)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station_key.capitalize()}*\nVarış: *{to_station_key.capitalize()}*\n\nLütfen bir *tarih* seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        elif prefix == 'date':
            action = parts[1]
            from_station_key = parts[2]
            to_station_key = parts[3]
            date_iso_str = parts[4]
            target_date = datetime.strptime(date_iso_str, "%Y-%m-%d")
            
            date_tr_str = target_date.strftime("%d %B %Y")
            await query.edit_message_text(
                text=f"Seçimleriniz:\n🚆 *{from_station_key.capitalize()}* ➡ *{to_station_key.capitalize()}*\n🗓 *{date_tr_str}*\n\nAPI sorgulanıyor, lütfen bekleyin...", 
                parse_mode='Markdown'
            )

            if action == "check":
                print(f"Callback -> check_api_once: {chat_id}, {from_station_key}, {to_station_key}, {target_date}")
                threading.Thread(
                    target=run_one_time_check,
                    args=(chat_id, from_station_key, to_station_key, target_date)
                ).start()
            
            elif action == "monitor":
                if chat_id in monitor_jobs:
                    await query.message.reply_text("Zaten aktif bir izlemeniz var. /stop")
                    return

                print(f"Callback -> monitor_api_loop: {chat_id}, {from_station_key}, {to_station_key}, {target_date}")
                check_interval = 30
                stop_event = threading.Event()
                monitor_thread = threading.Thread(
                    target=monitoring_loop,
                    args=(chat_id, stop_event, from_station_key, to_station_key, target_date, check_interval)
                )
                
                monitor_jobs[chat_id] = (monitor_thread, stop_event)
                monitor_thread.start()

    except Exception as e:
        print(f"Callback hatası: {e}")
        await query.message.reply_text(f"Buton işlemi sırasında bir hata oluştu: {e}")

def main():
    builder = Application.builder().token(TELEGRAM_API_TOKEN)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("monitor", monitor_command))
    app.add_handler(CommandHandler("stop", stop_command))
    
    app.add_handler(CallbackQueryHandler(button_callback, pattern='^(from_|to_|date_)'))

    print("API Tabanlı Bot başlatıldı...")
    app.run_polling()

if __name__ == "__main__":
    main()            