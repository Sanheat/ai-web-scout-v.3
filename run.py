import os
import subprocess
from sheets_export import export_to_sheets

def run_spider():
    print("▶ Шаг 1: Запуск поиска 3D-туров (Scrapy)...")
    # Запускаем паука через командную строку
    subprocess.run(["scrapy", "crawl", "site_spider"], check=True)

def run_export():
    print("▶ Шаг 2: Выгрузка результатов в Google Sheets...")
    if not os.path.exists("google_creds.json"):
        print("❌ Ошибка: Файл 'google_creds.json' не найден. Выгрузка в Google Sheets пропущена.")
        print("✅ Но не переживай! Все результаты сохранены в файл 'results.csv'.")
        return

    try:
        export_to_sheets()
        print("✅ Успех! Данные выгружены в Google Таблицы.")
    except Exception as e:
        print(f"❌ Ошибка при выгрузке в Google: {e}")

if __name__ == "__main__":
    try:
        run_spider()
        run_export()
    except Exception as e:
        print(f"🚨 Критическая ошибка проекта: {e}")