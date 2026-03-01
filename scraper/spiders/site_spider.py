import scrapy
from scrapy import signals
from urllib.parse import urlparse
import os
import sys

class SiteSpider(scrapy.Spider):
    name = "site_spider"
    
        def __init__(self, sites_file=None, user_query=None, keywords=None, *args, **kwargs):
        super(SiteSpider, self).__init__(*args, **kwargs)
        self.query = user_query
        self.keywords = [k.strip().lower() for k in keywords.split(",")] if keywords else []
        self.handled_sites = set()
        self.initial_sites = []
        
        # Счетчик страниц для каждого сайта
        self.page_counts = {} 
        self.MAX_PAGES_PER_SITE = 25

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

        # --- ШАГ 1: ЛОГИКА ПОИСКА С LLM ---
        content = response.text.lower()
        found = any(keyword in content for keyword in self.keywords)

        if found:
            # Добавляем корневую папку проекта в пути для Python
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if project_root not in sys.path:
                sys.path.append(project_root)
                
            from llm_validator import validate_with_llm
            api_key = os.getenv("OPENAI_API_KEY")
            
            if api_key:
                self.logger.info(f"🔎 Найдено совпадение по словам на: {response.url}. Запускаем ИИ-чтение...")
                
                # Заставляем ИИ прочитать текст страницы и поискать ответ
                extracted_data = validate_with_llm(
                    html_content=response.text, 
                    url=response.url, 
                    user_query=self.query, 
                    api_key=api_key
                )
                
                # Если ИИ нашел конкретный ответ и он не 'NO'
                if extracted_data and extracted_data.upper() != "NO":
                    self.logger.info(f"✅ Успех! ИИ извлек данные с {response.url}")
                    self.handled_sites.add(site_data['site'])
                    
                    yield {
                        'index': site_data.get('index', 0),
                        'site': site_data['site'],
                        'result': extracted_data,
                        'source_url': response.url
                    }
                    return
                else:
                    self.logger.info(f"🤖 Совадения по словам были, но ИИ не нашел точного ответа на {response.url}. Ищем дальше.")
            else:
                self.logger.error("❌ OPENAI_API_KEY не установлен!")
                self.handled_sites.add(site_data['site'])
                yield {
                    'index': site_data.get('index', 0),
                    'site': site_data['site'],
                    'result': response.url,
                    'source_url': response.url
                }
                return

        # --- ШАГ 2: УМНАЯ НАВИГАЦИЯ ПО САЙТУ ---
        if self.page_counts[domain] < self.MAX_PAGES_PER_SITE:
            a_elements = response.css('a')
            
            # Приоритетные слова для ссылок
            base_target_words = [
                'contact', 'about', 'team', 'company', 'people', 'info', 
                'контакт', 'нас', 'команд', 'связь', 'инфо', 'компани'
            ]
            target_words = base_target_words + self.keywords
            
            seen_urls = set()
            
            for a in a_elements:
                link = a.attrib.get('href')
                link_text = a.css('::text').get(default='').lower() 
                
                if not link or link.startswith(('javascript:', 'mailto:', 'tel:')):
                    continue
                    
                absolute_url = response.urljoin(link)
                
                # Переходим только по внутренним страницам (того же домена)
                if urlparse(absolute_url).netloc == domain and absolute_url not in seen_urls:
                    seen_urls.add(absolute_url)
                    
                    link_lower = absolute_url.lower()
                    is_priority = any(word in link_lower or word in link_text for word in target_words)
                    
                    # Даем высокий приоритет нужным страницам
                    req_priority = 100 if is_priority else -1
                    
                    yield scrapy.Request(
                        absolute_url,
                        callback=self.parse,
                        errback=self.handle_error,
                        meta={'site_data': site_data},
                        priority=req_priority,
                        dont_filter=False
                    )
        else:
            self.logger.info(f"Достигнут лимит в {self.MAX_PAGES_PER_SITE} страниц для {domain}")

    def handle_error(self, failure):
        self.logger.error(f"Ошибка при запросе: {repr(failure)}")

    def spider_idle(self):
        # Если паук простаивает (все ссылки обошли, новые не добавили)
        for site_data in self.initial_sites:
            if site_data['site'] not in self.handled_sites:
                self.handled_sites.add(site_data['site'])
                self.logger.info(f"Запись пустого результата для {site_data['site']}")
                # ИИ ничего не нашел или страницы не открылись
                # Записываем пустой результат вручную
