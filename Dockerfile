FROM python:3.12-slim

# Системные зависимости для lxml/scrapy (на случай отсутствия колёс)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Каталог под постоянную БД (смонтируйте сюда диск/том для durability)
RUN mkdir -p /data
ENV SCOUT_DB=/data/scout.db
ENV PORT=8000
EXPOSE 8000

# ВАЖНО: ровно 1 worker — api-key и блокировка запусков живут в памяти процесса,
# состояние в SQLite. Масштабирование по потокам (--threads), не по воркерам.
CMD ["sh", "-c", "gunicorn server:app --workers 1 --threads 8 --timeout 1800 --bind 0.0.0.0:${PORT:-8000}"]
