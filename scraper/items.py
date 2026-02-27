import scrapy

class SiteResultItem(scrapy.Item):
    site = scrapy.Field()
    result = scrapy.Field()
    index = scrapy.Field()  # Добавляем поле для порядка
