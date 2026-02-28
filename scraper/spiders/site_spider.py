import scrapy
from scrapy import signals
from urllib.parse import urlparse

class SiteSpider(scrapy.Spider):
    name = "site_spider"
    
    def __init__(self, sites_file=None, query=None, keywords=None, *args, **kwargs):
        super(SiteSpider, self).__init__(*args, **kwargs)
        self.query = query
        self.keywords = [k.strip().lower() for k in keywords.split(",")] if keywords else []
        self.handled_sites = set()
        self.initial_sites = []
        
        # --- НОВОЕ: Счетчик страниц для каждого сайта ---
        self.page_counts = {} 
        self.MAX_PAGES_PER_SITE = 25
        # -----------------------------------------------

        if sites_file:
            import pandas as pd
            df = pd.read_csv(sites_file)
            self.initial_sites = df.to_dict('records')

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(SiteSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_idle, signal=signals.spider_idle)
        return spider

    def start_requests(self):
        for site_data in self.initial_sites:
            url = site_data['site']
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Инициализируем счетчик для этого сайта
            domain = urlparse(url).netloc
            self.page_counts[domain] = 0
            
            yield scrapy.Request(
                url, 
                callback=self.parse, 
                errback=self.handle_error,
                meta={'site_data': site_data, 'depth': 0},
                dont_filter=True
            )

    def parse(self, response):
        site_data = response.meta.get('site_data')
        domain = urlparse(response.url).netloc
        
        # Увеличиваем счетчик посещенных страниц для этого домена
        self.page_counts[domain] = self.page_counts.get(domain, 0) + 1
        
        # Если мы уже нашли информацию на этом сайте — выходим
        if site_data['site'] in self.handled_sites:
            return

        # Логика поиска ключевых слов (как у тебя была)
        content = response.text.lower()
        found = any(keyword in content for keyword in self.keywords)

        if found:
            self.handled_sites.add(site_data['site'])
            yield {
                'index': site_data.get('index', 0),
                'site': site_data['site'],
                'result': response.url  # Или другой результат
            }
            return

        # --- ЛОГИКА ПЕРЕХОДА ПО ССЫЛКАМ ---
        # Проверяем лимит страниц для текущего домена
        if self.page_counts[domain] < self.MAX_PAGES_PER_SITE:
            links = response.css('a::attr(href)').getall()
            for link in links:
                absolute_url = response.urljoin(link)
                if urlparse(absolute_url).netloc == domain:
                    yield scrapy.Request(
                        absolute_url,
                        callback=self.parse,
                        errback=self.handle_error,
                        meta={'site_data': site_data}
                    )
        else:
            self.logger.info(f"Достигнут лимит в {self.MAX_PAGES_PER_SITE} страниц для {domain}")

    def handle_error(self, failure):
        # Твой текущий обработчик ошибок
        pass

    def spider_idle(self):
        # Твой текущий метод для записи пустых результатов
        pass
