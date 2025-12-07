FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT_BACKEND=8001 \
    PORT_UI=3000

WORKDIR /app

# Sistem bağımlılıkları (gerekirse genişletilebilir)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
  && rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama kodu
COPY backend ./backend
COPY ui ./ui

EXPOSE 8001 3000

# Varsayılan olarak sadece backend'i çalıştırıyoruz.
# Kubernetes tarafında UI pod'u için komut override edilerek
# streamlit başlangıcı verilecektir.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]


