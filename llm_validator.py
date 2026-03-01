import openai
import os
import re
import json
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import markdownify

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
    """Очищает HTML в Markdown и проверяет наличие информации с помощью ИИ. Возвращает строгий JSON."""
    
    # 1. Подстановка данных в запрос
    final_query = substitute_placeholders(user_query, url)
    
    # 2. Очистка контента: удаляем технический мусор через BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    for element in soup(["script", "style", "nav", "footer", "meta", "link", "noscript", "svg", "button", "input"]):
        element.decompose()
        
    # 3. Конвертируем очищенный HTML в чистый Markdown
    try:
        clean_markdown = markdownify.markdownify(str(soup), heading_style="ATX")
        clean_markdown = re.sub(r'\n{3,}', '\n\n', clean_markdown).strip()
    except Exception as e:
        print(f"Ошибка конвертации в Markdown: {e}")
        clean_markdown = soup.get_text(separator='\n', strip=True)

    text_sample = clean_markdown[:25000]

    # 4. Формируем промпт. Требуем строгий JSON.
    messages = [
        {
            "role": "system", 
            "content": """You are a professional web data extraction agent.
Your task is to extract exact information from the provided text based on the USER INSTRUCTIONS.
You must ALWAYS respond with a valid JSON object in the following format:
{
  "found": true or false,
  "data": "The exact extracted information, or null if nothing was found."
}
Do not include any extra text."""
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
            response_format={"type": "json_object"}, # 🔥 Включаем режим строгой отдачи JSON
            messages=messages,
            temperature=0
        )
        
        # 5. Парсим ответ из JSON-строки в Python словарь
        raw_json_str = response.choices[0].message.content.strip()
        result_dict = json.loads(raw_json_str)
        
        # 6. Проверяем, нашел ли ИИ что-то
        if result_dict.get("found") is True and result_dict.get("data"):
            return str(result_dict["data"])
        else:
            return None # "На этом сайте данных нет"
            
    except Exception as e:
        print(f"Ошибка OpenAI (или парсинга JSON): {e}")
        return None
