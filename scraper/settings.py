BOT_NAME = 'scraper'
SPIDER_MODULES = ['scraper.spiders']
NEWSPIDER_MODULE = 'scraper.spiders'

# Глубина поиска: 1 (главная + ссылки на ней). 
# Этого достаточно для большинства задач без ухода в дебри маркетплейсов.
DEPTH_LIMIT = 1

# --- СЕКЦИЯ СКОРОСТИ И АНОНИМНОСТИ ---
# Задержка между запросами
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True

# Настройки параллелизма
CONCURRENT_REQUESTS = 32
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_TIMEOUT = 15

# Повторы при ошибках
RETRY_ENABLED = True
RETRY_TIMES = 2

# --- ИГНОРИРОВАНИЕ МУСОРА ---
# Не качаем лишние файлы, чтобы не тратить лимит страниц (CLOSESPIDER_PAGECOUNT)
EXTENSIONS_TO_IGNORE = ['png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'doc', 'xlsx', 'zip', 'mp4', 'svg']

# Маскировка
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
ROBOTSTXT_OBEY = False

# --- ВЫВОД ДАННЫХ ---
# Мы не подключаем пайплайны здесь, так как записываем результат через команду -o в Streamlit (app.py)
ITEM_PIPELINES = {}

# --- ПРОКСИ (Если планируешь использовать) ---
# Если купишь прокси-шлюз, раскомментируй строки ниже:
# import os
# os.environ["http_proxy"] = "http://username:password@gate.proxy-service.com:8000"
# os.environ["https_proxy"] = "http://username:password@gate.proxy-service.com:8000"
