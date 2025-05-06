import gspread
from .. import config
import logging

# Инициализация клиента Google Sheets
try:
    client = gspread.service_account_from_dict(config.GOOGLE_CREDENTIALS)
    logging.info("Успешное подключение к Google Sheets API")
except Exception as e:
    logging.error(f"Ошибка при инициализации клиента Google Sheets: {e}")
    raise

# Получение листов
try:
    orders_sheet = client.open_by_key(config.ORDERS_SHEET_ID).sheet1
    users_sheet = client.open_by_key(config.USERS_SHEET_ID).sheet1
    auth_sheet = client.open_by_key(config.AUTH_SHEET_ID).sheet1
    logging.info("Успешное получение листов Google Sheets")
except Exception as e:
    logging.error(f"Ошибка при получении листов Google Sheets: {e}")
    raise 