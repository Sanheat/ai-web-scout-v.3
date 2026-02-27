import scrapy
import pandas as pd
import os
from urllib.parse import urlparse
from scrapy import signals
from scrapy.exceptions import DontCloseSpider
from llm_validator import validate_with_llm
from scraper.items import SiteResultItem

class SiteSpider(scrapy.Spider):
    name = "site_spider"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SiteSpider, cls).from_crawler(crawler, *args, **kwargs)
        # Подключаемся к сигналу "паук собирается закрыться"
        crawler.signals.connect(spider.spider_idle, signal=signals.spider_idle)
        return spider

    def __init__(self, user_query="", keywords="", api_key="", *args, **kwargs):
        super(SiteSpider, self).__init__(*args, **kwargs)
        self.user_query = user_query
        self.api_key = api_key
        self.keywords = [k.strip().lower() for k in keywords.split(",") if k.strip()] if keywords else []
        
        self.handled_sites = set()
        self.all_sites_list = [] # Здесь будем хранить абсолютно все сайты из исходника

    def start_requests(self):
        if os.path.exists("sites.csv"):
            df = pd.read_csv("sites.csv")
            for idx, site in enumerate(df['site'].tolist()):
                url = site.strip()
                if not url: continue
                if not url.startswith('http'): 
                    url = 'https://' + url
                
                # Запоминаем сайт, чтобы потом проверить, обработан ли он
                self.all_sites_list.append((url, idx))
                
                yield scrapy.Request(
                    url=url, 
                    callback=self.parse, 
                    errback=self.handle_error,
                    meta={'root_site': url, 'site_index': idx},
                    dont_filter=True
                )

    def parse(self, response):
        root_url = response.meta['root_site']
        idx = response.meta['site_index']
        
        # Если сайт уже успешно обработан, ничего не делаем
        if root_url in self.handled_sites:
            return

        html_content = response.text
        found_keywords = [word for word in self.keywords if word in html_content.lower()]
        
        if found_keywords:
            llm_answer = validate_with_llm(html_content, response.url, self.user_query, self.api_key)
            if llm_answer:
                self.handled_sites.add(root_url)
                yield SiteResultItem(site=root_url, result=llm_answer, index=idx)
                return 
        
        # Переход по внутренним ссылкам
        links = response.css('a::attr(href)').getall()
        for link in links:
            absolute_link = response.urljoin(link)
            parsed_link = urlparse(absolute_link)
            parsed_root = urlparse(root_url)
            
            if parsed_root.netloc.replace('www.', '') in parsed_link.netloc:
                yield response.follow(
                    absolute_link, 
                    callback=self.parse, 
                    errback=self.handle_error,
                    meta={'root_site': root_url, 'site_index': idx}
                )

    def handle_error(self, failure):
        root_url = failure.request.meta['root_site']
        idx = failure.request.meta['site_index']
        req_url = failure.request.url
        
        # Если упала главная страница, и сайт еще не записан в обработанные
        if req_url == root_url and root_url not in self.handled_sites:
            self.handled_sites.add(root_url)
            yield SiteResultItem(
                site=root_url, 
                result="Ошибка: Сайт недоступен (Timeout/DNS)", 
                index=idx
            )

    def spider_idle(self, spider):
        """Эта функция срабатывает, когда паук обошел все страницы и готовится выключиться"""
        requests_added = False
        
        for root_url, idx in self.all_sites_list:
            # Если по этому сайту мы так и не добились никакого ответа
            if root_url not in self.handled_sites:
                self.handled_sites.add(root_url) # Помечаем, чтобы избежать зацикливания
                
                # В Scrapy нельзя делать yield напрямую из spider_idle, 
                # поэтому мы кидаем внутреннему движку фейковый мгновенный запрос
                req = scrapy.Request(
                    "data:,", # Пустой протокольный URL, который обработается мгновенно
                    callback=self.parse_dummy, 
                    meta={'root_site': root_url, 'site_index': idx},
                    dont_filter=True
                )
                self.crawler.engine.crawl(req, spider)
                requests_added = True
                
        # Если мы добавили "потеряшек", говорим пауку "подожди, не закрывайся"
        if requests_added:
            raise DontCloseSpider("Добавляем пустые ответы для ненайденных сайтов")

    def parse_dummy(self, response):
        """Просто отдаем недостающую информацию"""
        root_url = response.meta['root_site']
        idx = response.meta['site_index']
        yield SiteResultItem(site=root_url, result="Информация не найдена", index=idx)
