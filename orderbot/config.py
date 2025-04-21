# config.py

import os
import base64
import json
import tempfile
import logging

# Настройка логирования должна быть первой
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
        logging.FileHandler('bot.log')  # Вывод в файл
    ]
)

# Настраиваем логирование для всех используемых библиотек
for logger_name in ['httpx', 'telegram', 'aiohttp']:
    logging.getLogger(logger_name).setLevel(logging.INFO)
    logging.getLogger(logger_name).propagate = True

# Загружаем переменные окружения из .env, если файл существует
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logging.info("python-dotenv не установлен, используем переменные окружения напрямую")

# Токен Telegram бота
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Настройки Google Sheets
GOOGLE_CREDENTIALS_BASE64 = os.environ.get('GOOGLE_CREDENTIALS_BASE64')
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
# Уникальные идентификаторы Google таблиц (не зависят от имени таблицы)
MENU_SHEET_ID = os.environ.get('MENU_SHEET_ID')
ORDERS_SHEET_ID = os.environ.get('ORDERS_SHEET_ID')

# Настройки для API Точка Банка
TOCHKA_JWT_TOKEN = os.environ.get('TOCHKA_JWT_TOKEN')
TOCHKA_CLIENT_ID = os.environ.get('TOCHKA_CLIENT_ID')
TOCHKA_ACCOUNT_ID = os.environ.get('TOCHKA_ACCOUNT_ID')
TOCHKA_MERCHANT_ID = os.environ.get('TOCHKA_MERCHANT_ID')

# Логгируем только при отсутствии важных переменных окружения
if not TOCHKA_JWT_TOKEN:
    logging.warning("TOCHKA_JWT_TOKEN не найден в переменных окружения")
if not TOCHKA_ACCOUNT_ID:
    logging.warning("TOCHKA_ACCOUNT_ID не найден в переменных окружения")
if not TOCHKA_MERCHANT_ID:
    logging.warning("TOCHKA_MERCHANT_ID не найден в переменных окружения")