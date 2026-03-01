import streamlit as st
import pandas as pd
import subprocess
import os

# Пытаемся импортировать функцию, если файл llm_validator существует
try:
    from llm_validator import get_keywords_from_query
except ImportError:
    st.error("Файл llm_validator.py не найден!")

st.set_page_config(page_title="AI Web Scout", page_icon="🔎", layout="wide")

st.title("🔎 AI Web Scout: Анализатор сайтов")

# --- БЛОК 1: НАСТРОЙКИ ---
with st.sidebar:
    st.header("Настройки")
    api_key = st.text_input("OpenAI API Key:", type="password")

# --- БЛОК 2: ВВОД ДАННЫХ ---
col1, col2 = st.columns([1, 1])
with col1:
    sites_input = st.text_area(
        "Список доменов:", 
        placeholder="example.com\ncompany.ru\nbrand.io\n\nПо одному домену на строку", 
        height=200
    )
with col2:
    user_query = st.text_area(
        "Что ищем?", 
        placeholder="Опишите, что нужно найти на сайтах компаний.\n\nНапример:\n— Email для связи с отделом продаж\n— Имя генерального директора\n— Адрес главного офиса", 
        height=200
    )

if st.button("🚀 Запустить поиск и анализ", use_container_width=True):
    if not api_key or not sites_input or not user_query:
        st.error("Заполните все поля!")
    else:
        # Очистка старых файлов перед запуском
        for f in ["results.csv", "sites.csv"]:
            if os.path.exists(f): 
                try:
                    os.remove(f)
                except:
                    pass
        
        sites = [s.strip() for s in sites_input.split('\n') if s.strip()]
        total_sites = len(sites)

        # Создаем временный файл со списком сайтов для паука
        pd.DataFrame(sites, columns=['site']).to_csv("sites.csv", index=False)

        # 1. Генерация ключевых слов через LLM
        with st.spinner("Генерация ключевых слов..."):
            try:
                keywords_list = get_keywords_from_query(user_query, api_key)
                keywords_str = ",".join(keywords_list)
                st.info(f"🔎 Ключевые слова для поиска: {keywords_str}")
            except Exception as e:
                st.error(f"Ошибка при генерации ключевых слов: {e}")
                st.stop()

        # 2. ЗАПУСК SCRAPY
        os.environ["OPENAI_API_KEY"] = api_key
        cmd = [
            "scrapy", "crawl", "site_spider", 
            "-a", f"sites_file=sites.csv",
            "-a", f"user_query={user_query}", 
            "-a", f"keywords={keywords_str}",
            "-o", "results.csv" 
        ]

        with st.spinner("Робот обходит сайты... это может занять несколько минут"):
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            with st.expander("📝 Посмотреть детальный лог работы паука (Scrapy Logs)"):
                if process.stderr:
                    st.code(process.stderr)
                if process.stdout:
                    st.code(process.stdout)
            
            if process.returncode != 0:
                st.error(f"Произошла критическая ошибка (Код завершения: {process.returncode}). Проверьте логи выше.")

        # 3. ОБРАБОТКА РЕЗУЛЬТАТОВ
        # Базовый датафрейм из ВСЕХ доменов в исходном порядке пользователя
        df_all = pd.DataFrame(sites, columns=['site'])

        if os.path.exists("results.csv"):
            try:
                df_res = pd.read_csv("results.csv")

                if not df_res.empty:
                    cols_available = [c for c in ['site', 'result', 'source_url'] if c in df_res.columns]
                    df_res = df_res[cols_available]
                    # Убираем дубли (один домен мог найтись на нескольких страницах)
                    df_res = df_res.drop_duplicates(subset='site', keep='first')
                    # LEFT JOIN: все домены + результаты где есть
                    df_merged = df_all.merge(df_res, on='site', how='left')
                else:
                    df_merged = df_all.copy()

            except pd.errors.EmptyDataError:
                df_merged = df_all.copy()
            except Exception as e:
                st.error(f"Ошибка при чтении результатов: {e}")
                df_merged = df_all.copy()
        else:
            st.error("Файл результатов не был создан. Посмотрите логи выше.")
            df_merged = df_all.copy()

        # Заполняем пустые ячейки для ненайденных доменов
        if 'result' not in df_merged.columns:
            df_merged['result'] = None
        df_merged['result'] = df_merged['result'].fillna('❌ Не найдено')

        if 'source_url' not in df_merged.columns:
            df_merged['source_url'] = None
        df_merged['source_url'] = df_merged['source_url'].fillna('—')

        # Статистика
        found_count = (df_merged['result'] != '❌ Не найдено').sum()
        if found_count == 0:
            st.warning(f"Поиск завершён, но информация ни по одному из {total_sites} доменов не найдена.")
        else:
            st.success(f"Готово! Найдено по {found_count} из {total_sites} доменов.")

        # Таблица со всеми доменами
        cols_to_show = [c for c in ['site', 'result', 'source_url'] if c in df_merged.columns]
        final_df = df_merged[cols_to_show].reset_index(drop=True)
        st.dataframe(final_df, use_container_width=True)

        # Кнопка скачивания — всегда доступна
        csv_data = final_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Скачать результаты (CSV)", csv_data, "scout_results.csv", "text/csv")
