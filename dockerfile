FROM python:3.12-slim

# Chromium ve gerekli bağımlılıkları yükle
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libgdk-pixbuf2.0-0 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxrandr2 \
    libasound2 \
    libxss1 \
    libxtst6

# Python bağımlılıklarını yükle
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

# Uygulamanın çalışacağı komut
CMD ["python", "e_bilet.py"]
