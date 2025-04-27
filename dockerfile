# Python 3.11 tabanlı bir base image kullanıyoruz
FROM python:3.11-slim

# Gereksinimler
RUN apt-get update -y && apt-get install -y \
    wget \
    curl \
    unzip \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libatk-1.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libu2f-udev

# Google Chrome'un en son sürümünü indir ve kur
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    dpkg -i google-chrome-stable_current_amd64.deb && \
    apt --fix-broken install -y

# Chrome sürümünü al
RUN CHROME_VERSION=$(google-chrome-stable --version | awk '{print $3}' | sed 's/\.[0-9]*$//') && \
    wget https://chromedriver.storage.googleapis.com/$(echo $CHROME_VERSION)/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/

# Çalışma dizinini belirle
WORKDIR /app

# Gerekli Python paketlerini yükle
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Çalıştırılacak Python dosyasını belirle
COPY . /app

# Botu çalıştır
CMD ["python", "e_bilet.py"]
