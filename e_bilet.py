import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import os

load_dotenv()

# Telegram Bot API Token ve Chat ID bilgilerinizi buraya ekleyin
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_ID_2 = os.getenv("TELEGRAM_CHAT_ID_2")


def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage'
    chat_ids = [TELEGRAM_CHAT_ID, TELEGRAM_CHAT_ID_2]
    payload = {
        'text': message,
        'parse_mode': 'Markdown'
    }
    for chat_id in chat_ids:
        payload['chat_id'] = chat_id
        try:
            response = requests.post(url, data=payload)
            if response.status_code == 200:
                print(f"Telegram mesajı {chat_id} için gönderildi.")
            else:
                print(f"Telegram mesajı {chat_id} için gönderilemedi:", response.text)
        except Exception as e:
            print(f"Telegram mesajı {chat_id} için gönderme hatası:", e)

def select_station(driver, input_id, station_name, index=0):
    try:
        input_element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, input_id))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", input_element)
        input_element.clear()
        input_element.send_keys(station_name)
        time.sleep(2)

        stations = WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, 'textLocation'))
        )

        for i, station in enumerate(stations):
            print(f"{i}: {station.text}")

        if stations and len(stations) > index:
            driver.execute_script("arguments[0].scrollIntoView(true);", stations[index])
            stations[index].click()
            print(f"Seçilen istasyon ({input_id}): {stations[index].text}")
        else:
            print(f"{station_name} için uygun istasyon bulunamadı.")
    except Exception as e:
        print(f"Hata ({input_id}):", e)

def select_date(driver, target_date: datetime):
    try:
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

        # 3. Hedef günü bul ve tıkla
        day_to_select = str(target_date.day)

        day_cells = driver.find_elements(By.CSS_SELECTOR, 'td')
        for cell in day_cells:
            if cell.text.strip() == day_to_select:
                cell.click()
                print(f"Takvimden tarih seçildi: {target_date.strftime('%d.%m.%Y')}")
                return

        print(f"Tarih hücresi bulunamadı: {target_date.strftime('%d.%m.%Y')}")
    except Exception as e:
        print("Takvimden tarih seçme hatası:", e)

def search_trips(driver):
    try:
        search_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, 'searchSeferButton'))
        )
        driver.execute_script("arguments[0].click();", search_button)
    except Exception as e:
        print("Sefer arama butonu hatası:", e)

def check_trips(driver):
    try:
        trips = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.XPATH, '//*[starts-with(@id, "gidis")]'))
        )
        
        if not trips:
            print("Sefer bulunamadı.")
            send_telegram_message("Bugün için bilet bulunamadı.")
            return

        trip_html_list = driver.execute_script('''return Array.from(document.querySelectorAll('[id^="collapseBodygidis"]')).map(el => el.innerHTML);''')

        target_time = datetime.strptime("20:30", "%H:%M").time()

        for trip_index, trip_html in enumerate(trip_html_list, start=1):
            soup = BeautifulSoup(trip_html, "html.parser")

            trip_name = soup.select("div.trainStationTimeArea span.mt-1")
            if len(trip_name) >= 2:
                departure = trip_name[0].text.strip()
                arrival = trip_name[1].text.strip()
            else:
                departure = arrival = "Bilinmiyor"

            time_info = soup.select_one("div.trainStationTimeArea time")
            time_text = time_info.text.strip() if time_info else "Saat bilgisi yok"

            match = re.search(r"(\d{2}:\d{2})", time_text)

            if match:
                departure_time_text = match.group(1)
            else:
                continue  # Saat formatı uygun değilse geç

            try:
                trip_time = datetime.strptime(departure_time_text, "%H:%M").time()
            except ValueError:
                continue
            
            # if trip_time <= target_time:
            #     continue              

            trip_title = f"{departure} ➡ {arrival} | {time_text}"
            print(trip_title)
            wagons = soup.find_all("button", class_="btnTicketType")
            message = f"Sefer {trip_index}: {trip_title}"

            available_wagons = False  # Dolu olmayan vagon sayısı kontrolü

            for wagon in wagons:
                wagon_type = wagon.find("span", class_="mb-0 text-left")
                wagon_type = wagon_type.text.strip() if wagon_type else "Bilinmiyor"

                status = wagon.find("p", class_="price")
                status = status.text.strip() if status else "DOLU"

                unwanted_types = ["TEKERLEKLİ SANDALYE", "YATAKLI", "LOCA"]

                # Eğer vagon dolu değilse, sadece o vagonu yazdır
                if status != "DOLU" and wagon_type not in unwanted_types:
                    available_wagons = True  # Eğer dolu olmayan bir vagon varsa, mesajı göndermek için true yap
                    message += f"\n  {wagon_type}: {status}"
                
            # Mesajda sadece boş vagonlar varsa, mesaj gönder
            if available_wagons:
                send_telegram_message(message)
            
    except Exception as e:
        print("Sefer kontrol hatası:", e)
        send_telegram_message(f"Sefer kontrol hatası: {e}")

def automate_check(driver, from_station, to_station, start_date, days_interval=1, check_interval_seconds=30):
    try:
        select_station(driver, 'fromTrainInput', from_station, index=2)
        time.sleep(2)
        select_station(driver, 'toTrainInput', to_station, index=8)
        time.sleep(2)
        current_date = start_date
        select_date(driver, current_date)
        time.sleep(2)
        search_trips(driver)
        time.sleep(2)
        check_trips(driver)
        time.sleep(2)

        while True:
            driver.refresh()  # Sayfayı yenile
            time.sleep(5)
            check_trips(driver)

            # Bir sonraki gün için tarih ayarlama
            current_date += timedelta(days=days_interval)
            print(f"Tarih güncelleniyor: {current_date.strftime('%d.%m.%Y')}")

            # Belirtilen saniye aralığında bekle
            print(f"Bir sonraki kontrol için {check_interval_seconds} saniye bekleniyor...")
            time.sleep(check_interval_seconds)  # Saniye olarak bekleme süresi
    except Exception as e:
        print(f"Genel hata: {e}")
        send_telegram_message(f"Genel hata: {e}")

if __name__ == "__main__":
    options = uc.ChromeOptions()
    options.add_argument('--headless')  # Railway headless çalışmalı
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    driver = uc.Chrome(headless=True, use_subprocess=True, options=options)
    driver.get('https://ebilet.tcddtasimacilik.gov.tr/')
    
    # Başlangıç tarihini ayarlayın
    start_date = datetime.now()
    
    # Otomatik kontrol başlat
    automate_check(driver, 'Sakarya', 'İstanbul', start_date, days_interval=0, check_interval_seconds=30)
