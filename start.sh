#!/bin/bash

echo "🚀 Paketler kontrol ediliyor..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🚀 Bot başlatılıyor..."
python3 e_bilet.py
