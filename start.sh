#!/bin/bash

echo "📦 Bağımlılıklar yükleniyor..."
apt-get update && apt-get install -y \
    wget \
    unzip \
    curl \
    gnupg \
    fonts-liberation \
    libasound2 \
    libnss3 \
    libxss1 \
    libxtst6 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libu2f-udev \
    ca-certificates \
    xdg-utils \
    chromium \
    chromium-driver \
    python3-pip

echo "🖥 Python paketleri kuruluyor..."
pip3 install --upgrade pip
pip3 install undetected-chromedriver selenium

echo "🚀 Bot başlatılıyor..."
python3 e_bilet.py