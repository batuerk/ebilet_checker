import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import re
import random
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os
import threading
import locale # <-- Türkçe tarihler için eklendi

# Telegram Bot Kütüphaneleri
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # <-- Butonlar için eklendi
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler # <-- Buton yakalayıcı eklendi

# --- LOKAL AYARI (TÜRKÇE TARİHLER İÇİN) ---
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'tr_TR')
    except locale.Error:
        print("Turkish locale (tr_TR) bulunamadı, varsayılan locale kullanılıyor. Tarihler İngilizce görünebilir.")
# ---------------------------------------------

# .env dosyasını yükle
load_dotenv()

# --- Global Ayarlar ---
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") 
monitor_jobs = {} # { chat_id: (threading.Thread, threading.Event) }

# --- YENİ: İSTASYON LİSTESİ ---
# select_station fonksiyonunun 'in' ile arama özelliğine güvenerek
# sade isimler kullanıyoruz.
STATIONS_OF_INTEREST = [
    "ARİFİYE", 
    "SAPANCA", 
    "İZMİT", 
    "GEBZE", 
    "PENDİK", 
    "BOSTANCI", 
    "SÖĞÜTLÜÇEŞME", 
    "BAKIRKÖY", 
    "HALKALI",
    "ERYAMAN",
    "POLATLI",
    "SİNCAN",
    "ANKARA GAR",
]
# -------------------------------

# --- Telegram Mesajlaşma ---
def send_telegram_message(message: str, chat_id: str):
    """(Thread içinden mesaj göndermek için)"""
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print(f"Telegram mesajı {chat_id} için gönderildi.")
        else:
            print(f"Telegram mesajı {chat_id} için gönderilemedi:", response.text)
    except Exception as e:
        print(f"Telegram mesajı {chat_id} için gönderme hatası:", e)

# --- Selenium Yardımcı Fonksiyonları (İyileştirilmiş) ---
def get_driver():
    """Headless çalışan bir Chrome driver başlatır."""
    options = uc.ChromeOptions()
    # options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    try:
        driver = uc.Chrome(headless=False, use_subprocess=True, options=options)
        driver.set_page_load_timeout(45)
        return driver
    except Exception as e:
        print(f"Driver başlatılamadı: {e}")
        return None

def select_station(driver, input_id, station_name):
    """İstasyon seçme işlemini, önce tam eşleşme, sonra kısmi eşleşme ile yapar."""
    try:
        input_element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, input_id))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", input_element)
        input_element.clear()
        input_element.send_keys(station_name)
        time.sleep(random.uniform(1.5, 2.5))

        stations = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, 'textLocation'))
        )
        
        # 1. Önce tam eşleşme ara (Büyük/küçük harf duyarsız)
        exact_match = None
        for station in stations:
            if station.text.lower() == station_name.lower():
                exact_match = station
                break
        
        if exact_match:
            selected_text = exact_match.text
            driver.execute_script("arguments[0].scrollIntoView(true);", exact_match)
            exact_match.click()
            print(f"Seçilen istasyon ({input_id}) [Tam Eşleşme]: {selected_text}")
            return True

        # 2. Tam eşleşme yoksa, 'in' ile ara (kısmi eşleşme)
        print(f"Tam eşleşme bulunamadı for '{station_name}', 'in' ile aranıyor...")
        for station in stations:
            # örn: 'söğütlüçeşme' araması 'istanbul(söğütlüçeşme)' içinde bulunur
            if station_name.lower() in station.text.lower():
                selected_text = station.text
                driver.execute_script("arguments[0].scrollIntoView(true);", station)
                station.click()
                print(f"Seçilen istasyon ({input_id}) [Kısmi Eşleşme]: {selected_text}")
                return True
        
        print(f"{station_name} için uygun istasyon bulunamadı.")
        return False
    except Exception as e:
        print(f"Hata ({input_id}):", e)
        return False

def select_date(driver, target_date: datetime):
    try:
        today = datetime.today() # Bugünün tarihini al
        # 1. Takvimi aç
        date_input = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '.form-control.calenderPurpleImg'))
        )
        driver.execute_script("arguments[0].click();", date_input)
        time.sleep(1)  # Takvimin yüklenmesini bekle

        # Gün hücrelerini bekle
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'td'))
        )

        # 2. Ay Kontrolü
        # Eğer hedef ay, bu aydan BÜYÜKSE, 'ileri' butonuna tıkla
        # (Yıl değişimi de kontrol ediliyor)
        if target_date.month > today.month or target_date.year > today.year:
            print("Hedef tarih bir sonraki ayda. 'İleri' butonuna tıklanıyor...")
            try:
                # Bootstrap datepicker 'ileri' butonu sınıfı
                next_button = driver.find_element(By.CSS_SELECTOR, '.next.available')
                next_button.click()
                # Ay değişim animasyonu için kısa bir bekleme
                time.sleep(random.uniform(0.5, 1.0))
            except Exception as e:
                print(f"Sonraki ay butonuna basılamadı: {e}")
                return False # Butonu bulamazsa hata ver

        # 3. Hedef günü bul ve tıkla
        day_to_select = str(target_date.day)
        found_day = False
        day_cells = driver.find_elements(By.CSS_SELECTOR, 'td')
        for cell in day_cells:
            if cell.text.strip() == day_to_select:
                cell.click()
                print(f"Takvimden tarih seçildi: {target_date.strftime('%d.%m.%Y')}")
                found_day = True
                return True # <- BAŞARI! (En önemli düzeltme)
        if not found_day:
            print(f"Tarih hücresi bulunamadı: {day_to_select}")
            return False # <- HATA    

        print(f"Tarih hücresi bulunamadı: {target_date.strftime('%d.%m.%Y')}")
    except Exception as e:
        print("Takvimden tarih seçme hatası:", e)

def search_trips(driver):
    """Sefer ara butonuna tıklar."""
    try:
        search_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, 'searchSeferButton'))
        )
        driver.execute_script("arguments[0].click();", search_button)
        print("Sefer ara butonuna tıklandı.")

        time.sleep(5)
        with open("sayfa.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.save_screenshot("sayfa.png")

        return True
    except Exception as e:
        print("Sefer arama butonu hatası:", e)
        return False

def check_trips(driver, chat_id_to_notify: str):
    try:
        # Önce "Sefer bulunamadı" mesajı var mı diye kontrol et
        try:
            no_trips_msg = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.textSeferDepartureFirst.mb-0'))
            )
            if no_trips_msg:
                print("🚫 O gün için hiç sefer kalmamış.")
                send_telegram_message("🚫 Bugün için tüm seferler tamamlanmış veya hiç sefer bulunmuyor.", chat_id_to_notify)
                return False
        except TimeoutException:
            # Mesaj yoksa sefer kontrolüne devam et
            pass

        trips = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, '//*[starts-with(@id, "gidis")]'))
        )
        time.sleep(random.uniform(2, 4))
        
        if not trips:
            print("Sefer bulunamadı.")
            send_telegram_message("Bugün için bilet bulunamadı.")
            return False

        trip_html_list = driver.execute_script('''return Array.from(document.querySelectorAll('[id^="collapseBodygidis"]')).map(el => el.innerHTML);''')

        target_time = datetime.strptime("20:30", "%H:%M").time()

        found_any_available_trip = False 
        for trip_index, trip_html in enumerate(trip_html_list, start=1):
            soup = BeautifulSoup(trip_html, "html.parser")
            
            trip_name = soup.select("div.trainStationTimeArea span.mt-1")
            departure = trip_name[0].text.strip() if len(trip_name) > 0 else "Bilinmiyor"
            arrival = trip_name[1].text.strip() if len(trip_name) > 1 else "Bilinmiyor"
            
            time_info = soup.select_one("div.trainStationTimeArea time")
            time_text = time_info.text.strip() if time_info else "Saat bilgisi yok"

            trip_title = f"*{departure} ➡ {arrival} | {time_text}*"
            message = f"🚆 Sefer Bulundu: {trip_title}"
            
            wagons = soup.find_all("button", class_="btnTicketType")
            available_wagons_in_this_trip = False 

            for wagon in wagons:
                wagon_type_element = wagon.find("span", class_="mb-0 text-left")
                wagon_type = wagon_type_element.text.strip() if wagon_type_element else "Bilinmiyor"

                status_element = wagon.find("p", class_="price")
                status = status_element.text.strip() if status_element else "DOLU"
                
                unwanted_types = ["TEKERLEKLİ SANDALYE", "YATAKLI", "LOCA"]

                if status != "DOLU" and wagon_type not in unwanted_types:
                    available_wagons_in_this_trip = True
                    message += f"\n  ✅ {wagon_type}: *{status}*"
            
            if available_wagons_in_this_trip:
                found_any_available_trip = True
                print(f"Boş yer bulundu: {trip_title}")
                send_telegram_message(message, chat_id_to_notify)

        return found_any_available_trip

    except Exception as e:
        print(f"Sefer kontrol hatası: {e}")
        send_telegram_message(f"Seferleri kontrol ederken bir hata oluştu: {e}", chat_id_to_notify)
        return False

# --- Ana İş Mantığı (Worker) ---
def monitoring_loop(chat_id: str, stop_event: threading.Event, from_station: str, to_station: str, target_date: datetime, interval_seconds: int):
    """
    Belirli bir kullanıcı için arka planda çalışan izleme döngüsü.
    """
    driver = get_driver()
    if not driver:
        send_telegram_message("Tarayıcı (Chrome Driver) başlatılamadı. İzleme durduruldu.", chat_id)
        return

    try:
        print(f"İzleme başladı: {chat_id} | {from_station} -> {to_station} | {target_date.strftime('%d.%m.%Y')}")
        driver.get('https://ebilet.tcddtasimacilik.gov.tr/')
        time.sleep(random.uniform(2, 4))

        if not select_station(driver, 'fromTrainInput', from_station):
            raise Exception(f"Kalkış istasyonu bulunamadı: {from_station}")
        time.sleep(random.uniform(1, 2))
        
        if not select_station(driver, 'toTrainInput', to_station):
            raise Exception(f"Varış istasyonu bulunamadı: {to_station}")
        time.sleep(random.uniform(1, 2))

        if not select_date(driver, target_date):
            raise Exception(f"Tarih seçilemedi: {target_date.strftime('%d.%m.%Y')}")
        time.sleep(random.uniform(1, 2))
        
        if not search_trips(driver):
            raise Exception("Sefer arama butonuna tıklanamadı.")

        while not stop_event.is_set():
            print(f"Kontrol ediliyor ({chat_id})...")
            check_trips(driver, chat_id) 
            print(f"{interval_seconds} saniye bekleniyor...")
            if stop_event.wait(interval_seconds):
                break
            
            driver.refresh()
            print("Sayfa yenilendi.")
            time.sleep(random.uniform(4, 7))

    except Exception as e:
        print(f"İzleme döngüsünde hata ({chat_id}): {e}")
        send_telegram_message(f"Bir hata oluştu, izleme durduruldu: {e}", chat_id)
    finally:
        driver.quit()
        print(f"Driver kapatıldı ({chat_id}).")
        if chat_id in monitor_jobs:
            del monitor_jobs[chat_id]
            print(f"İzleme işi listeden kaldırıldı ({chat_id}).")

def run_one_time_check(chat_id: str, from_station: str, to_station: str, target_date: datetime):
    """
    Sadece bir kez kontrol yapar ve sonucu bildirir.
    """
    driver = get_driver()
    if not driver:
        send_telegram_message("Tarayıcı (Chrome Driver) başlatılamadı. Kontrol başarısız.", chat_id)
        return
        
    print(f"Tek seferlik kontrol: {chat_id} | {from_station} -> {to_station} | {target_date.strftime('%d.%m.%Y')}")
    
    try:
        driver.get('https://ebilet.tcddtasimacilik.gov.tr/')
        time.sleep(random.uniform(2, 4))
        
        if not select_station(driver, 'fromTrainInput', from_station):
            raise Exception(f"Kalkış istasyonu bulunamadı: {from_station}")
        time.sleep(random.uniform(1, 2))
        if not select_station(driver, 'toTrainInput', to_station):
            raise Exception(f"Varış istasyonu bulunamadı: {to_station}")
        time.sleep(random.uniform(1, 2))
        if not select_date(driver, target_date):
            raise Exception(f"Tarih seçilemedi: {target_date.strftime('%d.%m.%Y')}")
        time.sleep(random.uniform(1, 2))
        if not search_trips(driver):
            raise Exception("Sefer arama butonuna tıklanamadı.")
            
        if not check_trips(driver, chat_id):
            send_telegram_message(
                f"Maalesef, {target_date.strftime('%d %B %Y')} tarihi için\n"
                f"*{from_station} ➡ {to_station}* yönüne boş yer bulunamadı.", 
                chat_id
            )
            
    except Exception as e:
        print(f"Tek seferlik kontrol hatası ({chat_id}): {e}")
        send_telegram_message(f"Kontrol sırasında bir hata oluştu: {e}", chat_id)
    finally:
        driver.quit()
        print(f"Driver kapatıldı (tek seferlik - {chat_id}).")

# --- KLAVYE OLUŞTURUCU FONKSİYONLAR (GÜNCELLENDİ) ---

def create_station_keyboard(action: str, from_station: str = None) -> InlineKeyboardMarkup:
    """Kalkış (step 1) veya Varış (step 2) istasyon butonlarını oluşturur."""
    keyboard = []
    row = []
    
    # Adım 2'deysek (varış seçimi), kalkış istasyonunu listeden çıkar
    if from_station:
        stations_to_show = [s for s in STATIONS_OF_INTEREST if s != from_station]
        prefix = f"to_{action}_{from_station}" # örn: "to_check_ARİFİYE"
    # Adım 1'deysek (kalkış seçimi)
    else:
        stations_to_show = STATIONS_OF_INTEREST
        prefix = f"from_{action}" # örn: "from_check"
        
    for station in stations_to_show:
        # callback_data: "from_check_ARİFİYE" veya "to_check_ARİFİYE_SÖĞÜTLÜÇEŞME"
        callback_data = f"{prefix}_{station}"
        row.append(InlineKeyboardButton(station.capitalize(), callback_data=callback_data))
        
        # Her satırda 2 istasyon
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row: # Kalanları ekle
        keyboard.append(row)
        
    return InlineKeyboardMarkup(keyboard)


def create_date_keyboard(action: str, from_station: str, to_station: str) -> InlineKeyboardMarkup:
    """(Adım 3) 12 gün için tarih seçme butonları oluşturur."""
    keyboard = []
    today = datetime.today()
    
    row = []
    for i in range(0, 13): 
        day = today + timedelta(days=i)
        date_str_iso = day.strftime("%Y-%m-%d")
        
        # callback_data: "date_check_ARİFİYE_SÖĞÜTLÜÇEŞME_2025-10-26"
        callback_data = f"date_{action}_{from_station}_{to_station}_{date_str_iso}"
        
        if i == 1:
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

# --- Telegram Bot Komutları (GÜNCELLENDİ) ---

async def start(update: Update, context: CallbackContext):
    """/start komutu (Güncellenmiş yardım metni)"""
    message = """
👋 Merhaba! Ben TCDD Bilet Takip Botuyum.

Senin için istediğin seferleri sürekli kontrol edebilirim.

*KOMUTLAR:*
• `/check` - Tek seferlik bilet kontrolü için adımları başlatır.
• `/monitor` - Sürekli bilet takibi için adımları başlatır.
• `/stop` - Aktif izlemeyi durdurur.

Kalkış, varış ve tarih bilgilerini komutu verdikten sonra seçeceksin.
    """
    await update.message.reply_text(message, parse_mode='Markdown')

async def check_command(update: Update, context: CallbackContext):
    """/check komutu - Adım 1'i (kalkış seçimi) başlatır."""
    keyboard = create_station_keyboard(action="check")
    await update.message.reply_text(
        "Lütfen *kalkış* istasyonunu seçin:", 
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

async def monitor_command(update: Update, context: CallbackContext):
    """/monitor komutu - Adım 1'i (kalkış seçimi) başlatır."""
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
    """/stop komutu - (Değişiklik yok)"""
    chat_id = str(update.message.chat_id)
    
    if chat_id in monitor_jobs:
        monitor_thread, stop_event = monitor_jobs.pop(chat_id)
        print(f"Durdurma sinyali gönderiliyor: {chat_id}")
        stop_event.set()
        await update.message.reply_text("İzleme durduruluyor... 🛑")
    else:
        await update.message.reply_text("Aktif bir izlemeniz bulunmuyor.")

# --- YENİ: Ana Buton Yakalayıcı (Tüm adımları yönetir) ---
async def button_callback(update: Update, context: CallbackContext):
    """Tüm inline butonlara basıldığında tetiklenir."""
    query = update.callback_query
    await query.answer() # Butona basma hissini vermek için anında cevap ver
    
    chat_id = str(query.message.chat_id)
    
    try:
        # Gelen veriyi '_' ile ayır
        parts = query.data.split('_')
        prefix = parts[0] # 'from', 'to', veya 'date'

        # --- ADIM 1: Kalkış istasyonu seçildi ---
        if prefix == 'from':
            # "from_check_ARİFİYE"
            action = parts[1]
            from_station = parts[2]
            
            # Adım 2 klavyesini (varış) oluştur
            keyboard = create_station_keyboard(action=action, from_station=from_station)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station.capitalize()}*\n\nŞimdi *varış* istasyonunu seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        # --- ADIM 2: Varış istasyonu seçildi ---
        elif prefix == 'to':
            # "to_check_ARİFİYE_SÖĞÜTLÜÇEŞME"
            action = parts[1]
            from_station = parts[2]
            to_station = parts[3]
            
            # Adım 3 klavyesini (tarih) oluştur
            keyboard = create_date_keyboard(action=action, from_station=from_station, to_station=to_station)
            await query.edit_message_text(
                text=f"Kalkış: *{from_station.capitalize()}*\nVarış: *{to_station.capitalize()}*\n\nLütfen bir *tarih* seçin:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            
        # --- ADIM 3: Tarih seçildi (FİNAL) ---
        elif prefix == 'date':
            # "date_check_ARİFİYE_SÖĞÜTLÜÇEŞME_2025-10-26"
            action = parts[1]
            from_station = parts[2]
            to_station = parts[3]
            date_iso_str = parts[4]
            target_date = datetime.strptime(date_iso_str, "%Y-%m-%d")
            
            date_tr_str = target_date.strftime("%d %B %Y")
            await query.edit_message_text(
                text=f"Seçimleriniz:\n🚆 *{from_station.capitalize()}* ➡ *{to_station.capitalize()}*\n🗓 *{date_tr_str}*\n\nİşlem başlatılıyor...", 
                parse_mode='Markdown'
            )

            # Eyleme göre ilgili worker'ı (thread) başlat
            if action == "check":
                print(f"Callback -> check_command: {chat_id}, {from_station}, {to_station}, {target_date}")
                threading.Thread(
                    target=run_one_time_check, 
                    args=(chat_id, from_station, to_station, target_date)
                ).start()
            
            elif action == "monitor":
                if chat_id in monitor_jobs:
                    await query.message.reply_text("Zaten aktif bir izlemeniz var. /stop")
                    return

                print(f"Callback -> monitor_command: {chat_id}, {from_station}, {to_station}, {target_date}")
                check_interval = 30
                stop_event = threading.Event()
                monitor_thread = threading.Thread(
                    target=monitoring_loop,
                    args=(chat_id, stop_event, from_station, to_station, target_date, check_interval)
                )
                
                monitor_jobs[chat_id] = (monitor_thread, stop_event)
                monitor_thread.start()

    except Exception as e:
        print(f"Callback hatası: {e}")
        await query.message.reply_text(f"Buton işlemi sırasında bir hata oluştu: {e}")

# --- Botu Başlatma (GÜNCELLENDİ) ---
def main():
    if not TELEGRAM_API_TOKEN:
        print("HATA: TELEGRAM_API_TOKEN bulunamadı. Lütfen .env dosyanızı kontrol edin.")
        return

    builder = Application.builder().token(TELEGRAM_API_TOKEN)
    app = builder.build()

    # Komut handler'ları
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("monitor", monitor_command))
    app.add_handler(CommandHandler("stop", stop_command))
    
    # --- YENİ ANA BUTON HANDLER'I ---
    # "from_", "to_" VEYA "date_" ile başlayan tüm callback'leri yakalar
    app.add_handler(CallbackQueryHandler(button_callback, pattern='^(from_|to_|date_)'))
    # -----------------------------------

    print("Bot başlatıldı...")
    app.run_polling()

if __name__ == "__main__":
    main()