#!/bin/bash

# Sistem paketlerini güncelle ve Chrome'u kur
apt update && apt install -y wget gnupg unzip curl fonts-liberation libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 libnss3 libxcomposite1 libxcursor1 libxdamage1 libxrandr2 xdg-utils libgbm1 libasound2 libxshmfence1 libxss1 --no-install-recommends

# Chrome'u indir ve kur
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt install -y ./google-chrome-stable_current_amd64.deb

# Python dosyasını çalıştır
python3 e_bilet.py
