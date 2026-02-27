import scrapy
import pandas as pd
import os
from llm_validator import validate_with_llm
from scraper.items import SiteResultItem

class SiteSpider(scrapy.Spider):
    name = "site_spider"

    def __init__(self, user_query="", keywords="", api_key="", *args, **kwargs):
        super(SiteSpider, self).__init__(*args, **kwargs)
        self.user_query = user_query
        self.api_key = api_key
        self.keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()] if keywords else []

    def start_requests(self):
        if os.path.exists("sites.csv"):
            df = pd.read_csv("sites.csv")
            for idx, site in enumerate(df['site'].tolist()):
                url = site.strip()
                if not url: continue
                if not url.startswith('http'): url = 'https://' + url
                
                yield scrapy.Request(
                    url=url, 
                    callback=self.parse, 
                    # ДОБАВЛЯЕМ errback для обработки ошибок (DNS, Timeout и т.д.)
                    errback=self.handle_error,
                    meta={'root_site': url, 'site_index': idx},
                    dont_filter=True
                )

    def parse(self, response):
        root_url = response.meta['root_site']
        idx = response.meta['site_index']
        html_content = response.text
        
        result_text = "Информации не найдено"
        found_keywords = [word for word in self.keywords if word in html_content.lower()]
        
        if found_keywords:
            llm_answer = validate_with_llm(html_content, root_url, self.user_query, self.api_key)
            if llm_answer:
                result_text = llm_answer
        
        yield SiteResultItem(site=root_url, result=result_text, index=idx)

    # НОВАЯ ФУНКЦИЯ: Обработка упавших сайтов
    def handle_error(self, failure):
        root_url = failure.request.meta['root_site']
        idx = failure.request.meta['site_index']
        yield SiteResultItem(
            site=root_url, 
            result="Ошибка: Сайт недоступен (Timeout/DNS)", 
            index=idx
        )
