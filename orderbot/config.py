# config.py

import os
import base64
import json
import tempfile
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
        logging.FileHandler('bot.log')  # Вывод в файл
    ]
)

# Загружаем переменные окружения
load_dotenv()

# Токен Telegram бота
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Настройки Google Sheets
GOOGLE_CREDENTIALS_BASE64 = os.getenv('GOOGLE_CREDENTIALS_BASE64')
if GOOGLE_CREDENTIALS_BASE64:
    # Декодируем credentials из base64 и сохраняем во временный файл
    credentials_json = base64.b64decode(GOOGLE_CREDENTIALS_BASE64)
    temp_credentials = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
    temp_credentials.write(credentials_json)
    temp_credentials.close()
    GOOGLE_CREDENTIALS_FILE = temp_credentials.name
else:
    GOOGLE_CREDENTIALS_FILE = 'credentials.json'

GOOGLE_SHEETS_SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
MENU_SHEET_NAME = os.getenv('MENU_SHEET_NAME')
ORDERS_SHEET_NAME = os.getenv('ORDERS_SHEET_NAME')
