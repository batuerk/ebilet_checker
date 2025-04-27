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
    libxss1 \
    apt-transport-https \
    ca-certificates \
    libcurl4-openssl-dev

# Google Chrome'u indir ve kur
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# Chrome sürümünü al ve uyumlu ChromeDriver'ı indir
RUN CHROME_VERSION=$(google-chrome-stable --version | grep -oP '\d+\.\d+' | head -1) && \
    wget https://chromedriver.storage.googleapis.com/$(echo $CHROME_VERSION)/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip -d /usr/local/bin && \
    rm chromedriver_linux64.zip

# Python bağımlılıklarını yükle
COPY requirements.txt .
RUN pip install -r requirements.txt

# Kodları kopyala
COPY . .

# Uygulamayı başlat
CMD ["python3", "e_bilet.py"]
