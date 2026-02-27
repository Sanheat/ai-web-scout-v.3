import openai
import os
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def get_company_name_from_url(url):
    """Извлекает название компании из URL (домен без tld)."""
    try:
        domain = urlparse(url).netloc
        if not domain:
            domain = urlparse("https://" + url).netloc
        name = domain.split('.')[-2] if len(domain.split('.')) >= 2 else domain
        return name.upper()
    except:
        return "the company"

def substitute_placeholders(text, url):
    """Заменяет {{Company Name}} и {{Website}} на реальные данные."""
    company_name = get_company_name_from_url(url)
    text = text.replace("{{Company Name}}", company_name)
    text = text.replace("{{Website}}", url)
    return text

def get_keywords_from_query(user_query, api_key):
    """Генерирует ключевые слова для предварительной фильтрации сайтов."""
    client = openai.OpenAI(api_key=api_key)
    
    # Очищаем запрос от плейсхолдеров для генерации общих ключей
    clean_query = user_query.replace("{{Company Name}}", "company").replace("{{Website}}", "site")
    
    prompt = f"На основе запроса '{clean_query}' выдели 5-7 ключевых слов (существительных в начальной форме) для поиска на сайте через запятую. Только слова."
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return [k.strip().lower() for k in response.choices[0].message.content.split(",")]
    except:
        return [user_query.lower()]

def validate_with_llm(html_content, url, user_query, api_key):
    """Очищает HTML и проверяет наличие информации с помощью ИИ."""
    
    # 1. Подстановка данных в запрос
    final_query = substitute_placeholders(user_query, url)
    
    # 2. Очистка контента: выжимаем только полезный текст
    soup = BeautifulSoup(html_content, "html.parser")
    for script_or_style in soup(["script", "style", "nav", "footer"]):
        script_or_style.decompose()
    
    clean_text = soup.get_text(separator=' ', strip=True)
    text_sample = clean_text[:12000] # Увеличили лимит для более глубокого анализа

    # 3. Формируем промпт. Используем системную роль для инструкций, чтобы они не конфликтовали с пользовательским вводом.
    messages = [
        {
            "role": "system", 
            "content": "You are a professional web analyst. Your task is to extract specific information from the provided text based on the user's instructions. If the information is not present, reply exactly with 'NO'."
        },
        {
            "role": "user", 
            "content": f"USER INSTRUCTIONS:\n{final_query}\n\nPAGE URL: {url}\n\nPAGE CONTENT:\n{text_sample}"
        }
    ]

    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0
        )
        ans = response.choices[0].message.content.strip()
        
        # 4. Логика очистки ответа
        if ans.upper().startswith("YES:"): # На всякий случай
            ans = ans[4:].strip()
        
        if ans.upper() == "NO" or ans == "—" or not ans:
            return None
            
        return ans 
    except Exception as e:
        print(f"Ошибка OpenAI: {e}")
        return None
