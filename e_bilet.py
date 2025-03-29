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
print(TELEGRAM_API_TOKEN)
print(TELEGRAM_CHAT_ID)

def send_telegram_message(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print("Telegram mesajı gönderildi.")
        else:
            print("Telegram mesajı gönderilemedi:", response.text)
    except Exception as e:
        print("Telegram mesajı gönderme hatası:", e)

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

        if stations and len(stations) > index:
            driver.execute_script("arguments[0].scrollIntoView(true);", stations[index])
            stations[index].click()
            print(f"Seçilen istasyon ({input_id}): {stations[index].text}")
        else:
            print(f"{station_name} için uygun istasyon bulunamadı.")
    except Exception as e:
        print(f"Hata ({input_id}):", e)

def select_date(driver, date):
    try:
        # Tarih seçim kutusunu bulun
        date_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '.form-control.calenderPurpleImg'))
        )

        # JavaScript ile tarih ayarlama
        driver.execute_script("arguments[0].value = arguments[1];", date_input, date.strftime("%d.%m.%Y"))
        print(f"Tarih seçildi: {date.strftime('%d.%m.%Y')}")
    except Exception as e:
        print(f"Tarih seçme hatası:", e)


def search_trips(driver):
    try:
        search_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, 'searchSeferButton'))
        )
        search_button.click()
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
        
        for trip_index, trip_html in enumerate(trip_html_list, start=1):
            soup = BeautifulSoup(trip_html, "html.parser")
            wagons = soup.find_all("button", class_="btnTicketType")
            
            message = f"Sefer {trip_index}:"
            for wagon in wagons:
                wagon_type = wagon.find("span", class_="mb-0 text-left")
                wagon_type = wagon_type.text.strip() if wagon_type else "Bilinmiyor"

                status = wagon.find("p", class_="price")
                status = status.text.strip() if status else "DOLU"
                
                message += f"\n  {wagon_type}: {status}"

            send_telegram_message(message)
            
    except Exception as e:
        print("Sefer kontrol hatası:", e)
        send_telegram_message(f"Sefer kontrol hatası: {e}")

def automate_check(driver, from_station, to_station, start_date, days_interval=1, check_interval_minutes=30):
    try:
        select_station(driver, 'fromTrainInput', from_station, index=4)
        time.sleep(2)
        select_station(driver, 'toTrainInput', to_station, index=10)
        time.sleep(2)

        current_date = start_date
        while True:
            select_date(driver, current_date)
            time.sleep(2)
            search_trips(driver)
            time.sleep(2)
            check_trips(driver)
            
            # Bir sonraki gün için tarih ayarlama
            current_date += timedelta(days=days_interval)
            print(f"Tarih güncelleniyor: {current_date.strftime('%d.%m.%Y')}")

            # Belirtilen dakika aralığında bekle
            print(f"Bir sonraki kontrol için {check_interval_minutes} dakika bekleniyor...")
            time.sleep(check_interval_minutes * 60)  # Dakika olarak bekleme süresi
    except Exception as e:
        print(f"Genel hata: {e}")
        send_telegram_message(f"Genel hata: {e}")

if __name__ == "__main__":
    driver = uc.Chrome(headless=True, use_subprocess=False)
    driver.get('https://ebilet.tcddtasimacilik.gov.tr/')
    
    # Başlangıç tarihini ayarlayın
    start_date = datetime.now()
    
    # Otomatik kontrol başlat
    automate_check(driver, 'İstanbul', 'Sakarya', start_date, days_interval=0, check_interval_minutes=30)
