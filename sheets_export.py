import gspread
from oauth2client.service_account import ServiceAccountCredentials
import csv
import os

def export_to_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Авторизация
    creds = ServiceAccountCredentials.from_json_keyfile_name("google_creds.json", scope)
    client = gspread.authorize(creds)

    # Открываем таблицу (Убедись, что ты дал доступ сервисному email-у к этой таблице!)
    # Название таблицы должно точно совпадать
    sheet = client.open("3D Tours Results").sheet1
    sheet.clear()

    if not os.path.exists("results.csv"):
        print("Результаты не найдены (результаты.csv отсутствует)")
        return

    with open("results.csv", encoding='utf-8') as f:
        reader = csv.reader(f)
        rows = list(reader)
        if rows:
            sheet.insert_rows(rows)