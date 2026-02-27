BOT_NAME = 'scraper'
SPIDER_MODULES = ['scraper.spiders']
NEWSPIDER_MODULE = 'scraper.spiders'

# --- СЕКЦИЯ СКОРОСТИ И ГИБКОСТИ ---
# Увеличиваем задержку, чтобы сайты меньше блокировали (ошибки 503)
DOWNLOAD_DELAY = 1.5
# Добавляем случайное отклонение от задержки (от 0.75 до 2.25 сек), чтобы имитировать человека
RANDOMIZE_DOWNLOAD_DELAY = True

# Настройки параллелизма
CONCURRENT_REQUESTS = 32
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_TIMEOUT = 15
RETRY_ENABLED = True # Включаем повторы, так как теперь мы идем медленнее
RETRY_TIMES = 2

# --- ОГРАНИЧЕНИЯ ---
# Глубина 1: проверяем только главную и ссылки, которые на ней нашли
DEPTH_LIMIT = 1

# Список расширений, которые мы полностью игнорируем (картинки, документы)
EXTENSIONS_TO_IGNORE = ['png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'doc', 'xlsx', 'zip', 'mp4', 'svg']

# Маскировка под обычный браузер
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
ROBOTSTXT_OBEY = False

# Подключение Pipeline для записи в CSV
ITEM_PIPELINES = {
    # 'scraper.pipelines.CsvPipeline': 300,  <-- ЗАКОММЕНТИРУЙ ЭТО!
}
