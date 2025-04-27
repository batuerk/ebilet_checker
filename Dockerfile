# Temel Python 3.9 slim imajı
FROM python:3.9-slim

# Gerekli paketlerin kurulumu
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

# Google Chrome'u indirip kur
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install -y ./google-chrome-stable_current_amd64.deb && \
    rm google-chrome-stable_current_amd64.deb

# Chrome sürümünü öğren ve uyumlu ChromeDriver'ı indir
RUN CHROME_VERSION=$(google-chrome-stable --version | awk '{print $3}' | cut -d'.' -f1,2) && \
    echo "Chrome Version: $CHROME_VERSION" && \
    wget https://chromedriver.storage.googleapis.com/${CHROME_VERSION}/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip -d /usr/local/bin && \
    rm chromedriver_linux64.zip

# Sürüm numarasını Docker logs'ta görmek için yazdır
RUN echo "Installed Chrome Version: $CHROME_VERSION" > /chrome_version.txt

# Çalıştırılacak komut (örneğin bir Python uygulaması başlatılabilir)
CMD ["python3", "e_bilet.py"]
