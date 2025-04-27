#!/bin/bash

echo "📦 Bağımlılıklar yükleniyor..."
apt-get update && apt-get install -y wget curl unzip

echo "🖥 Chrome indiriliyor..."
wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
dpkg -i google-chrome-stable_current_amd64.deb || apt-get -f install -y

echo "🔧 ChromeDriver indiriliyor..."
CHROME_VERSION=$(google-chrome --version | awk '{print $3}')
CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION")
wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip"
unzip chromedriver_linux64.zip -d /usr/local/bin/
chmod +x /usr/local/bin/chromedriver

echo "🚀 Bot başlatılıyor..."
python3 bot.py 