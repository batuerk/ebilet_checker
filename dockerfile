FROM python:3.9-slim

# Gerekli sistem kütüphanelerini yükle
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    fonts-liberation \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libnss3 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libxss1

# Chrome indir ve kur
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# Python bağımlılıkları
COPY requirements.txt .
RUN pip install -r requirements.txt

# Kodları kopyala
COPY . .

# Uygulamayı başlat
CMD ["python3", "e_bilet.py"]
