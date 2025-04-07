from datetime import datetime, date
from .sheets import auth_sheet, spreadsheet
import logging
import gspread

# Получаем или создаем лист с авторизацией
try:
    auth_sheet = spreadsheet.worksheet("Auth")
except gspread.exceptions.WorksheetNotFound:
    auth_sheet = spreadsheet.add_worksheet("Auth", 1000, 2)
    # Добавляем заголовки
    auth_sheet.update('A1:B1', [['Phone Number', 'User ID']])

def is_user_authorized(user_id: str) -> bool:
    """Проверка, авторизован ли пользователь по его user_id."""
    try:
        # Получаем все значения из столбца B (user_id)
        user_ids = auth_sheet.col_values(2)
        return str(user_id) in user_ids
    except Exception as e:
        print(f"Ошибка при проверке авторизации пользователя: {e}")
        return False

def check_phone(phone: str) -> bool:
    """Проверка наличия телефона в базе."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = auth_sheet.col_values(1)
        return phone in phones
    except Exception as e:
        print(f"Ошибка при проверке телефона: {e}")
        return False

def save_user_id(phone: str, user_id: str) -> bool:
    """Сохранение user_id рядом с телефоном."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = auth_sheet.col_values(1)
        # Ищем индекс строки с нужным телефоном
        row_idx = phones.index(phone) + 1  # +1 потому что в gspread строки начинаются с 1
        # Обновляем ячейку с user_id (столбец B)
        auth_sheet.update_cell(row_idx, 2, user_id)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении user_id: {e}")
        return False 