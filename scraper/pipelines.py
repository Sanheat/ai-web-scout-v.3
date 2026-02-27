import csv

class CsvPipeline:
    def open_spider(self, spider):
        # Открываем файл в режиме дополнения (a), чтобы не стирать старое, если нужно
        self.file = open('results.csv', 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['site', 'result'])
        self.file.flush() # Сразу записываем заголовок на диск

    def close_spider(self, spider):
        self.file.close()

    def process_item(self, item, spider):
        self.writer.writerow([item['site'], item['result']])
        self.file.flush() # МГНОВЕННО записываем каждую найденную строку
        return item