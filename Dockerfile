FROM python:3.9-slim

# Locale ve timezone için gerekli paketler
RUN apt-get update && apt-get install -y \
    locales \
    tzdata \
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
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Timezone: Europe/Istanbul
ENV TZ=Europe/Istanbul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Locale: Turkish (UTF-8)
RUN sed -i 's/# tr_TR.UTF-8 UTF-8/tr_TR.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen

# Locale environment değişkenleri
ENV LANG=tr_TR.UTF-8 \
    LANGUAGE=tr_TR:tr \
    LC_ALL=tr_TR.UTF-8

# Python bağımlılıklarını yükle
COPY requirements.txt .
RUN pip install -r requirements.txt

# Kodları kopyala
COPY . .

# Uygulamayı başlat
CMD ["python3", "e_bilet_V3.py"]
