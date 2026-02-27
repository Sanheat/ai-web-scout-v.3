import streamlit as st
import pandas as pd
import subprocess
import os
from llm_validator import get_keywords_from_query

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
            if os.path.exists(f): os.remove(f)
        
        sites = [s.strip() for s in sites_input.split('\n') if s.strip()]
        pd.DataFrame(sites, columns=['site']).to_csv("sites.csv", index=False)

        # 1. Ключевые слова
        with st.spinner("Генерация ключевых слов..."):
            keywords_list = get_keywords_from_query(user_query, api_key)
            keywords_str = ",".join(keywords_list)
            st.info(f"🔎 Ключи: {keywords_str}")

        # 2. ЗАПУСК SCRAPY (с флагом -o для автоматического создания CSV)
        os.environ["OPENAI_API_KEY"] = api_key
        cmd = [
            "scrapy", "crawl", "site_spider", 
            "-a", f"user_query={user_query}", 
            "-a", f"keywords={keywords_str}",
            "-a", f"api_key={api_key}",
            "-o", "results.csv"  # ЗАСТАВЛЯЕМ SCRAPY ПИСАТЬ ВСЕ ПОЛЯ САМОМУ
        ]

        with st.spinner("Робот в процессе..."):
            process = subprocess.run(cmd, capture_output=True, text=True)
            if process.stderr:
                with st.expander("📝 Логи"): st.code(process.stderr)

        # 3. ОБРАБОТКА РЕЗУЛЬТАТОВ
        if os.path.exists("results.csv"):
            df_res = pd.read_csv("results.csv")
            
            # Проверяем, есть ли колонка index (теперь она точно будет)
            if 'index' in df_res.columns:
                # Превращаем в числа и сортируем
                df_res['index'] = pd.to_numeric(df_res['index'])
                df_res = df_res.sort_values(by="index")
                
                st.success(f"Готово! Обработано сайтов: {len(df_res)}")
                
                # Убираем колонку index из отображения, оставляем только суть
                final_df = df_res[["site", "result"]].reset_index(drop=True)
                st.dataframe(final_df, use_container_width=True)

                csv_data = final_df.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Скачать CSV", csv_data, "scout_results.csv", "text/csv")
            else:
                st.error("Колонка 'index' не найдена в результатах. Проверь SiteSpider.")
        else:
            st.warning("Результаты не записаны.")
