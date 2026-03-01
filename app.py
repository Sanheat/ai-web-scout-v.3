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
    sites_input = st.text_area("Список доменов:", placeholder="eattery.ru\nmiratorg.ru", height=200)
with col2:
    user_query = st.text_area("Что ищем?", placeholder="Адрес офиса компании...", height=200)

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
        # Добавляем путь к sites.csv, чтобы паук знал, что парсить
        cmd = [
            "scrapy", "crawl", "site_spider", 
            "-a", f"sites_file=sites.csv",
            "-a", f"user_query={user_query}", 
            "-a", f"keywords={keywords_str}",
            "-o", "results.csv" 
        ]

        with st.spinner("Робот обходит сайты... это может занять несколько минут"):
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            # ВАЖНО: Всегда показываем логи, чтобы понимать, что происходит внутри
            with st.expander("📝 Посмотреть детальный лог работы паука (Scrapy Logs)"):
                if process.stderr:
                    st.code(process.stderr)
                if process.stdout:
                    st.code(process.stdout)
            
            # Если код завершения не равен 0, значит произошла критическая ошибка
            if process.returncode != 0:
                st.error(f"Произошла критическая ошибка (Код завершения: {process.returncode}). Проверьте логи выше.")

        # 3. ОБРАБОТКА РЕЗУЛЬТАТОВ
        if os.path.exists("results.csv"):
            try:
                df_res = pd.read_csv("results.csv")
                
                if df_res.empty:
                    st.warning("Поиск завершен, но подходящая информация на сайтах не найдена.")
                else:
                    # Если есть колонка index, сортируем по ней
                    if 'index' in df_res.columns:
                        df_res['index'] = pd.to_numeric(df_res['index'], errors='coerce')
                        df_res = df_res.sort_values(by="index")
                    
                    st.success(f"Готово! Найдено совпадений: {len(df_res)}")
                    
                    # Показываем таблицу (выбираем нужные колонки, если они есть)
                    cols_to_show = [c for c in ["site", "result", "source_url"] if c in df_res.columns]

                    final_df = df_res[cols_to_show].reset_index(drop=True)
                    st.dataframe(final_df, use_container_width=True)

                    # Кнопка скачивания
                    csv_data = final_df.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Скачать результаты (CSV)", csv_data, "scout_results.csv", "text/csv")
                    
            except pd.errors.EmptyDataError:
                st.warning("Робот закончил работу, но файл результатов пуст (ничего не найдено).")
            except Exception as e:
                st.error(f"Ошибка при чтении результатов: {e}")
        else:
            st.error("Файл результатов не был создан. Возможно, конфигурация паука нарушена. Посмотрите логи выше.")
