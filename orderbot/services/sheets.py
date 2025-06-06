import gspread
from .. import config
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from functools import lru_cache
import base64
import json
import os
import logging
from ..utils.profiler import profile_time

# Подключаемся к Google Sheets
client = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)

# Открываем таблицу заказов
spreadsheet = client.open_by_key(config.ORDERS_SPREADSHEET_ID)

# ID листов
ORDERS_SHEET_ID = 2082646960
USERS_SHEET_ID = 505696272
KITCHEN_SHEET_ID = 2090492372
REC_SHEET_ID = 1331625926
AUTH_SHEET_ID = 66851994
MENU_SHEET_ID = 1181156289
COMPOSITION_SHEET_ID = 1127521486  # ID листа с составом блюд
TODAY_MENU_SHEET_ID = 1169304186   # ID листа с меню на сегодня
QUESTIONS_SHEET_ID = 1085408822    # ID листа с вопросами
ADMINS_SHEET_ID = 497772348        # ID листа с администраторами
PAYMENTS_SHEET_ID = 1774741525     # ID листа с оплатами

@profile_time
def get_orders_sheet():
    """Получение листа заказов."""
    try:
        return spreadsheet.get_worksheet_by_id(ORDERS_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Orders", 1000, 12)
        sheet.update('A1:L1', [['ID заказа', 'Время', 'Статус', 'User ID', 'Username',
                              'Сумма заказа', 'Номер комнаты', 'Имя',
                              'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи']])
        return sheet

@profile_time
def get_users_sheet():
    """Получение листа пользователей."""
    try:
        logging.info(f"Пытаемся получить лист пользователей по ID: {USERS_SHEET_ID}")
        sheet = spreadsheet.get_worksheet_by_id(USERS_SHEET_ID)
        logging.info(f"Успешно получен лист: {sheet.title}")
        return sheet
    except gspread.WorksheetNotFound as e:
        logging.warning(f"Лист не найден: {e}")
        logging.info("Создаем новый лист Users")
        sheet = spreadsheet.add_worksheet("Users", 1000, 11)  # Уменьшаем количество столбцов с 12 до 11
        sheet.update('A1:K1', [['User ID', 'Profile Link', 'First Name', 
                              'Phone Number', 'Room Number',
                              'Orders Count', 'Cancellations', 
                              'Total Sum', 'Unpaid Sum',
                              'Start Time', 'Last Order Date']])
        return sheet
    except Exception as e:
        logging.error(f"Неожиданная ошибка при получении листа пользователей: {e}")
        raise

@profile_time
def get_kitchen_sheet():
    """Получение листа кухни."""
    try:
        return spreadsheet.get_worksheet_by_id(KITCHEN_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Kitchen", 100, 1)
        sheet.update('A1', [['User ID']])
        return sheet

@profile_time
def get_rec_sheet():
    """Получение листа записей."""
    try:
        return spreadsheet.get_worksheet_by_id(REC_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Rec", 1000, 6)
        sheet.update('A1:F1', [['Дата', 'Количество заказов', 'Общая сумма', 
                              'Средний чек', 'Количество отмен', 'Процент отмен']])
        return sheet

@profile_time
def get_auth_sheet():
    """Получение листа авторизации."""
    try:
        return spreadsheet.get_worksheet_by_id(AUTH_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Auth", 1000, 4)
        sheet.update('A1:D1', [['Name', 'Phone Number', 'Room Number', 'User ID']])
        return sheet

@profile_time
def get_menu_sheet():
    """Получение листа меню."""
    return client.open_by_key(config.MENU_SPREADSHEET_ID).get_worksheet_by_id(MENU_SHEET_ID)

@profile_time
def get_composition_sheet():
    """Получение листа с составом блюд."""
    return client.open_by_key(config.MENU_SPREADSHEET_ID).get_worksheet_by_id(COMPOSITION_SHEET_ID)

@profile_time
def get_questions_sheet():
    """Получение листа вопросов."""
    try:
        return spreadsheet.get_worksheet_by_id(QUESTIONS_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Questions", 1000, 4)
        sheet.update('A1:D1', [['Дата', 'Пользователь', 'Телефон', 'Вопрос']])
        return sheet

@profile_time
def get_admins_sheet():
    """Получение листа администраторов."""
    try:
        return spreadsheet.get_worksheet_by_id(ADMINS_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Admins", 100, 2)
        sheet.update('A1:B1', [['Admin ID', 'Имя админа']])
        return sheet

# Кэш для меню
_menu_cache: Dict[str, List[Tuple[str, str, str]]] = {}
_last_menu_update = None
_MENU_CACHE_TTL = 86400  # 24 часа в секундах

@profile_time
def _update_menu_cache(force=False):
    """Обновление кэша меню.
    
    Args:
        force: Если True, принудительно обновляет кэш, игнорируя время последнего обновления.
    """
    global _last_menu_update
    current_time = datetime.now().timestamp()
    
    # Если кэш пустой или устарел, или требуется принудительное обновление
    if force or not _last_menu_update or (current_time - _last_menu_update) > _MENU_CACHE_TTL:
        column_map = {
            'Завтрак': (1, 2, 3),  # A, B и C столбцы
            'Обед': (4, 5, 6),      # D, E и F столбцы
            'Ужин': (7, 8, 9)      # G, H и I столбцы
        }
        
        menu_sheet = get_menu_sheet()
        for meal_type, (dish_col, price_col, weight_col) in column_map.items():
            dishes = menu_sheet.col_values(dish_col)[1:]
            prices = menu_sheet.col_values(price_col)[1:]
            weights = menu_sheet.col_values(weight_col)[1:]
            _menu_cache[meal_type] = list(zip(dishes, prices, weights))
        
        _last_menu_update = current_time
        logging.info(f"Кэш меню обновлен в {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")

@lru_cache(maxsize=100)
@profile_time
def get_dishes_for_meal(meal_type: str) -> List[Tuple[str, str, str]]:
    """Получение списка блюд с ценами и весом порций для выбранного типа еды."""
    _update_menu_cache()
    return _menu_cache.get(meal_type, [])

def get_next_order_id():
    """Получение следующего ID заказа.
    
    Returns:
        str: Следующий доступный ID заказа.
    """
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    if len(all_orders) <= 1:
        return "1"
    return str(int(all_orders[-1][0]) + 1)

@profile_time
async def save_order(order_data):
    """Сохраняет новый заказ в таблицу."""
    try:
        # Получаем следующий ID заказа (без await)
        next_id = get_next_order_id()
        
        # Форматируем дату и время
        timestamp = datetime.strptime(order_data['timestamp'], "%Y-%m-%d %H:%M:%S")
        formatted_timestamp = timestamp.strftime("%d.%m.%Y %H:%M:%S")
        
        # Формируем строку для записи
        row = [
            next_id,  # ID заказа
            formatted_timestamp,  # Время создания в формате DD.MM.YYYY HH:MM:SS
            order_data['status'],  # Статус заказа
            order_data['user_id'],  # ID пользователя
            order_data.get('username', ''),  # Имя пользователя в Telegram
            order_data.get('total_price', 0),  # Общая сумма
            order_data['room'],  # Номер комнаты
            order_data['name'],  # Имя заказчика
            order_data['meal_type'],  # Тип приема пищи
            ', '.join(f"{dish} x{order_data['quantities'].get(dish, 1)}" for dish in order_data['dishes']),  # Список блюд с количеством
            order_data.get('wishes', '—'),  # Пожелания
            order_data.get('delivery_date', '')  # Дата выдачи заказа
        ]
        
        # Добавляем заказ в таблицу с value_input_option='USER_ENTERED'
        get_orders_sheet().append_row(row, value_input_option='USER_ENTERED')
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при сохранении заказа: {e}")
        return False

@profile_time
async def update_order(order_id, row_index, order_data):
    """Обновляет существующий заказ в таблице."""
    try:
        # Получаем текущие данные заказа
        current_order = get_orders_sheet().row_values(row_index)
        
        # Обновляем только те поля, которые переданы в order_data
        if 'status' in order_data:
            current_order[2] = order_data['status']
        if 'room' in order_data:
            current_order[6] = order_data['room']
        if 'name' in order_data:
            current_order[7] = order_data['name']
        if 'meal_type' in order_data:
            current_order[8] = order_data['meal_type']
        if 'dishes' in order_data:
            current_order[9] = ', '.join(f"{dish} x{order_data['quantities'].get(dish, 1)}" for dish in order_data['dishes'])
        if 'wishes' in order_data:
            current_order[10] = order_data.get('wishes', '—')
        if 'delivery_date' in order_data:
            current_order[11] = order_data['delivery_date']
        
        # Обновляем строку в таблице с value_input_option='USER_ENTERED'
        get_orders_sheet().update(f'A{row_index}:L{row_index}', [current_order], value_input_option='USER_ENTERED')
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при обновлении заказа: {e}")
        return False

@profile_time
async def get_user_orders(user_id: str) -> List[List[str]]:
    """Получение всех активных заказов пользователя."""
    try:
        all_orders = get_orders_sheet().get_all_values()
        return [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Активен', 'Принят', 'Ожидает оплаты']]
    except Exception as e:
        logging.error(f"Ошибка при получении заказов пользователя: {e}")
        return []

async def update_order_status(order_id: str, row_idx: int, status: str) -> bool:
    """Обновление статуса заказа."""
    try:
        get_orders_sheet().update_cell(row_idx, 3, status)  # Колонка C содержит статус
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса заказа: {e}")
        return False

async def save_user_info(user_info: dict):
    """Сохранение информации о пользователе."""
    try:
        user_id = user_info['user_id']
        username = user_info.get('username', '-')
        profile_link = f"t.me/{username}" if username != '-' else '-'
        
        logging.info(f"Сохраняем информацию о пользователе {user_id}")
        
        # Проверяем, существует ли пользователь
        users_sheet = get_users_sheet()
        users_data = users_sheet.get_all_values()
        logging.info(f"Получено {len(users_data)} строк из листа пользователей")
        
        # Получаем имя из таблицы Auth
        auth_name = '-'
        try:
            auth_data = get_auth_sheet().get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                    auth_name = row[0] or '-'  # Берем имя из первого столбца
                    break
        except Exception as e:
            logging.error(f"Ошибка при получении имени из таблицы Auth: {e}")
        
        user_exists = False
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                logging.info(f"Найден существующий пользователь в строке {idx + 1}")
                # Обновляем существующего пользователя
                users_sheet.update(f'A{idx+1}:C{idx+1}', 
                                 [[user_id, profile_link, auth_name]],
                                 value_input_option='USER_ENTERED')
                user_exists = True
                logging.info("Информация о пользователе обновлена")
                break
        
        if not user_exists:
            logging.info("Создаем новую запись о пользователе")
            # Добавляем нового пользователя с новой структурой
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_user_row = [
                user_id,
                profile_link,
                auth_name,   # Имя из таблицы Auth
                '-',         # Phone Number
                '',          # Room Number (было Start Time)
                '0',         # Orders Count
                '0',         # Cancellations
                '0',         # Total Sum
                '0',         # Unpaid Sum (новый столбец)
                now,         # Start Time
                ''           # Last Order Date
            ]
            
            # Используем явное указание диапазона для добавления новой строки
            next_row = len(users_data) + 1
            users_sheet.update(f'A{next_row}:K{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новый пользователь добавлен в строку {next_row}")
        
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении информации о пользователе: {e}")
        return False

async def get_user_stats(user_id: str):
    """Получение статистики пользователя."""
    try:
        users_data = get_users_sheet().get_all_values()
        for row in users_data[1:]:  # Пропускаем заголовок
            if row[0] == user_id:
                return {
                    'orders_count': int(row[5]),  # Orders Count (сдвинуто влево)
                    'cancellations': int(row[6]),  # Cancellations (сдвинуто влево)
                    'total_sum': int(float(row[7])),  # Total Sum (сдвинуто влево)
                    'unpaid_sum': int(float(row[8] or '0')),  # Unpaid Sum (сдвинуто влево)
                    'last_order_date': row[10]  # Last Order Date (сдвинуто влево)
                }
        return None
    except Exception as e:
        logging.error(f"Ошибка при получении статистики пользователя: {e}")
        return None

def is_user_cook(user_id: str) -> bool:
    """Проверяет, является ли пользователь поваром."""
    try:
        # Получаем все ID поваров из первого столбца
        cook_ids = get_kitchen_sheet().col_values(1)
        return str(user_id) in cook_ids
    except Exception as e:
        logging.error(f"Ошибка при проверке доступа повара: {e}")
        return False

def is_user_admin(user_id: str) -> bool:
    """Проверяет, является ли пользователь администратором.
    
    Args:
        user_id: ID пользователя для проверки
        
    Returns:
        bool: True если пользователь является администратором, False в противном случае
    """
    try:
        # Получаем все ID администраторов из первого столбца
        admin_ids = get_admins_ids()
        return str(user_id) in admin_ids
    except Exception as e:
        logging.error(f"Ошибка при проверке доступа администратора: {e}")
        return False

def is_order_from_today(order_date_str: str) -> bool:
    """Проверяет, является ли заказ заказом на текущий день."""
    try:
        order_date = datetime.strptime(order_date_str, "%d.%m.%Y %H:%M:%S")
        today = datetime.now().date()
        return order_date.date() == today
    except ValueError:
        return False

async def update_orders_status():
    """Обновляет статусы заказов после полуночи."""
    try:
        # Получаем все заказы
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        today = datetime.now().date()
        
        # Создаем список для пакетного обновления
        updates = []
        
        # Пропускаем заголовок и обрабатываем каждый заказ
        for idx, order in enumerate(all_orders[1:], start=2):
            # Проверяем, что заказ активен
            if order[2] == 'Активен':
                # Получаем дату выдачи заказа
                delivery_date_str = order[11]  # Дата выдачи в последнем столбце
                if delivery_date_str:  # Проверяем, что дата выдачи указана
                    try:
                        # Парсим дату в формате DD.MM.YY
                        delivery_date = datetime.strptime(delivery_date_str, "%d.%m.%y").date()
                        # Если заказ на текущий день, добавляем в список для обновления
                        if delivery_date == today:
                            updates.append(idx)
                    except ValueError:
                        logging.error(f"Ошибка при парсинге даты выдачи заказа {order[0]}: {delivery_date_str}")
                        continue
        
        # Если есть заказы для обновления, выполняем пакетное обновление
        if updates:
            # Сортируем индексы строк
            updates.sort()
            
            # Группируем последовательные индексы
            ranges = []
            current_range = []
            
            for idx in updates:
                if not current_range or idx == current_range[-1] + 1:
                    current_range.append(idx)
                else:
                    # Если последовательность прервалась, сохраняем текущий диапазон
                    if len(current_range) == 1:
                        ranges.append((f'C{current_range[0]}', [['Принят']]))
                    else:
                        ranges.append((
                            f'C{current_range[0]}:C{current_range[-1]}',
                            [['Принят']] * len(current_range)
                        ))
                    current_range = [idx]
            
            # Добавляем последний диапазон
            if current_range:
                if len(current_range) == 1:
                    ranges.append((f'C{current_range[0]}', [['Принят']]))
                else:
                    ranges.append((
                        f'C{current_range[0]}:C{current_range[-1]}',
                        [['Принят']] * len(current_range)
                    ))
            
            # Выполняем пакетное обновление
            for range_name, values in ranges:
                orders_sheet.update(range_name, values, value_input_option='USER_ENTERED')
        
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статусов заказов: {e}")
        return False

async def update_orders_to_awaiting_payment():
    """Обновляет статусы заказов на "Ожидает оплаты" в указанное время дня выдачи.
    
    Заказы со статусом "Принят" обновляются до "Ожидает оплаты" в день выдачи в следующее время:
    - Заказы завтрака: 9:00
    - Заказы обеда: 14:00
    - Заказы ужина: 19:00
    """
    try:
        # Получаем текущую дату и время
        now = datetime.now()
        today = now.date()
        current_hour = now.hour
        
        # Определяем, какой тип еды нужно проверять в данный момент
        meal_type_to_check = None
        if current_hour == 9:
            meal_type_to_check = "Завтрак"
        elif current_hour == 14:
            meal_type_to_check = "Обед"
        elif current_hour == 19:
            meal_type_to_check = "Ужин"
        
        # Если текущее время не совпадает с временем обновления для какого-либо типа еды, выходим
        if not meal_type_to_check:
            logging.info(f"Сейчас не время обновления статусов заказов на 'Ожидает оплаты' ({current_hour}:00)")
            return True
        
        # Получаем все заказы
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        
        # Создаем список для пакетного обновления
        updates = []
        
        # Пропускаем заголовок и обрабатываем каждый заказ
        for idx, order in enumerate(all_orders[1:], start=2):
            # Проверяем, что заказ имеет статус "Принят" и соответствует нужному типу еды
            if order[2] == 'Принят' and order[8] == meal_type_to_check:
                # Получаем дату выдачи заказа
                delivery_date_str = order[11]  # Дата выдачи в последнем столбце
                if delivery_date_str:  # Проверяем, что дата выдачи указана
                    try:
                        # Парсим дату в формате DD.MM.YY
                        delivery_date = datetime.strptime(delivery_date_str, "%d.%m.%y").date()
                        # Если заказ на текущий день, добавляем в список для обновления
                        if delivery_date == today:
                            updates.append(idx)
                            logging.info(f"Заказ {order[0]} ({meal_type_to_check}) будет обновлен до 'Ожидает оплаты'")
                    except ValueError:
                        logging.error(f"Ошибка при парсинге даты выдачи заказа {order[0]}: {delivery_date_str}")
                        continue
        
        # Если есть заказы для обновления, выполняем пакетное обновление
        if updates:
            # Сортируем индексы строк
            updates.sort()
            
            # Группируем последовательные индексы
            ranges = []
            current_range = []
            
            for idx in updates:
                if not current_range or idx == current_range[-1] + 1:
                    current_range.append(idx)
                else:
                    # Если последовательность прервалась, сохраняем текущий диапазон
                    if len(current_range) == 1:
                        ranges.append((f'C{current_range[0]}', [['Ожидает оплаты']]))
                    else:
                        ranges.append((
                            f'C{current_range[0]}:C{current_range[-1]}',
                            [['Ожидает оплаты']] * len(current_range)
                        ))
                    current_range = [idx]
            
            # Добавляем последний диапазон
            if current_range:
                if len(current_range) == 1:
                    ranges.append((f'C{current_range[0]}', [['Ожидает оплаты']]))
                else:
                    ranges.append((
                        f'C{current_range[0]}:C{current_range[-1]}',
                        [['Ожидает оплаты']] * len(current_range)
                    ))
            
            # Выполняем пакетное обновление
            for range_name, values in ranges:
                orders_sheet.update(range_name, values, value_input_option='USER_ENTERED')
            
            logging.info(f"Обновлено {len(updates)} заказов типа {meal_type_to_check} на статус 'Ожидает оплаты'")
        else:
            logging.info(f"Нет заказов типа {meal_type_to_check} для обновления на статус 'Ожидает оплаты'")
        
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статусов заказов на 'Ожидает оплаты': {e}")
        return False

async def check_orders_awaiting_payment_at_startup():
    """Проверяет и обновляет статусы заказов, требующих смены статуса на 'Ожидает оплаты' при запуске бота.
    
    Функция вызывается после обновления статусов с 'Активен' на 'Принят'.
    Она проверяет заказы со статусом 'Принят' и:
    1. Для заказов прошлых дней (до сегодня, но не старше 5 дней) - меняет статус на 'Ожидает оплаты' без дополнительных проверок
    2. Для заказов сегодняшнего дня - проверяет тип еды и текущее время:
       - Заказы завтрака: после 9:00
       - Заказы обеда: после 14:00
       - Заказы ужина: после 19:00
    """
    try:
        # Получаем текущую дату и время
        now = datetime.now()
        today = now.date()
        current_hour = now.hour
        
        # Рассчитываем дату 5 дней назад
        five_days_ago = today - timedelta(days=5)
        
        logging.info(f"Проверка заказов для обновления до 'Ожидает оплаты'. Текущее время: {now.strftime('%Y-%m-%d %H:%M:%S')}, hour: {current_hour}")
        logging.info(f"Будут проверены заказы начиная с даты: {five_days_ago.strftime('%d.%m.%y')}")
        
        # Получаем все заказы
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        
        logging.info(f"Получено {len(all_orders)} строк заказов")
        
        # Создаем список для пакетного обновления
        updates = []
        
        # Словарь для определения, какие типы еды нужно обновить в зависимости от времени
        # Используем русские названия типов еды
        meal_types_to_check = {
            "Завтрак": current_hour >= 9,
            "Обед": current_hour >= 14,
            "Ужин": current_hour >= 19
        }
        
        logging.info(f"Статусы проверки для типов еды: {meal_types_to_check}")
        
        # Проходим по всем заказам и проверяем, нужно ли обновлять их статус
        for idx, order in enumerate(all_orders[1:], start=2):
            # Подробный лог для отладки
            logging.info(f"Проверка заказа {idx}: ID={order[0]}, Статус={order[2]}, Тип={order[8] if len(order) > 8 else 'N/A'}, Дата выдачи={order[11] if len(order) > 11 else 'N/A'}")
            
            # Проверяем, что заказ имеет статус "Принят"
            if order[2] == 'Принят':
                meal_type = order[8]  # Тип еды в 9-м столбце
                
                # Получаем дату выдачи заказа
                delivery_date_str = order[11]  # Дата выдачи в последнем столбце
                if delivery_date_str:  # Проверяем, что дата выдачи указана
                    try:
                        # Парсим дату в формате DD.MM.YY
                        delivery_date = datetime.strptime(delivery_date_str, "%d.%m.%y").date()
                        
                        # Пропускаем заказы старше 5 дней
                        if delivery_date < five_days_ago:
                            logging.info(f"Заказ {order[0]} пропущен: дата выдачи {delivery_date_str} старше 5 дней")
                            continue
                        
                        # Проверяем условия
                        is_today = delivery_date == today
                        is_past_day = delivery_date < today and delivery_date >= five_days_ago
                        is_valid_meal_type = meal_type in meal_types_to_check
                        is_time_passed = is_valid_meal_type and meal_types_to_check[meal_type]
                        
                        logging.info(f"Условия для заказа {order[0]}: is_today={is_today}, is_past_day={is_past_day}, is_valid_meal_type={is_valid_meal_type}, is_time_passed={is_time_passed}")
                        
                        # Если заказ на прошлый день (не старше 5 дней) - безусловно обновляем до "Ожидает оплаты"
                        if is_past_day:
                            updates.append(idx)
                            logging.info(f"Заказ {order[0]} (прошлый день: {delivery_date_str}) будет обновлен до 'Ожидает оплаты' при запуске")
                        # Если заказ на текущий день и время уже прошло порог для этого типа еды
                        elif is_today and is_valid_meal_type and is_time_passed:
                            updates.append(idx)
                            logging.info(f"Заказ {order[0]} ({meal_type}, сегодня) будет обновлен до 'Ожидает оплаты' при запуске")
                        else:
                            logging.info(f"Заказ {order[0]} ({meal_type}) не будет обновлен: не соответствует условиям")
                    except ValueError:
                        logging.error(f"Ошибка при парсинге даты выдачи заказа {order[0]}: {delivery_date_str}")
                        continue
                else:
                    logging.info(f"Заказ {order[0]} не будет обновлен: отсутствует дата выдачи")
            else:
                logging.info(f"Заказ {order[0]} не будет обновлен: статус не 'Принят', а '{order[2]}'")
        
        logging.info(f"Заказы для обновления: {updates}")
        
        # Если есть заказы для обновления, выполняем обновления по отдельности для каждого заказа
        if updates:
            # Обновляем каждый заказ по отдельности для максимальной точности и предсказуемости
            actual_updates = []
            for idx in updates:
                # Проверяем еще раз, чтобы убедиться, что заказ все еще требует обновления
                try:
                    # Индекс в списке all_orders
                    order_idx = idx - 1  # Номер строки - 1
                    
                    # Проверяем, что индекс не выходит за границы
                    if order_idx < 0 or order_idx >= len(all_orders):
                        logging.error(f"Индекс {order_idx} за пределами массива all_orders (длина {len(all_orders)})")
                        continue
                        
                    order = all_orders[order_idx]
                    
                    logging.info(f"Перепроверка заказа {idx} (индекс {order_idx}): {order}")
                    
                    # Проверяем статус и тип еды
                    if len(order) <= 8 or len(order) <= 11:
                        logging.warning(f"Заказ {idx} (индекс {order_idx}) не имеет достаточно полей: {order}")
                        continue
                        
                    # Проверяем, что это заказ со статусом "Принят"
                    if order[2] != 'Принят':
                        logging.warning(f"Заказ {idx} (индекс {order_idx}) имеет статус {order[2]}, а не 'Принят'")
                        continue
                        
                    # Получаем дату выдачи заказа
                    delivery_date_str = order[11]
                    if not delivery_date_str:
                        logging.warning(f"Заказ {idx} (индекс {order_idx}) не имеет даты выдачи")
                        continue
                        
                    # Парсим дату в формате DD.MM.YY
                    try:
                        delivery_date = datetime.strptime(delivery_date_str, "%d.%m.%y").date()
                        
                        # Еще раз проверяем, что заказ не старше 5 дней
                        if delivery_date < five_days_ago:
                            logging.warning(f"Заказ {idx} (индекс {order_idx}) имеет дату {delivery_date_str}, которая старше 5 дней")
                            continue
                        
                        # Для прошлых дней обновляем без дополнительных проверок
                        if delivery_date < today:
                            # Если все проверки пройдены, обновляем заказ
                            logging.info(f"Перепроверка пройдена для заказа {idx} (индекс {order_idx}). Обновляем до 'Ожидает оплаты' (прошлый день)")
                            orders_sheet.update(f'C{idx}', [['Ожидает оплаты']], value_input_option='USER_ENTERED')
                            logging.info(f"Заказ в строке {idx} обновлен до 'Ожидает оплаты' при запуске бота (прошлый день)")
                            actual_updates.append(idx)
                            continue
                    except ValueError:
                        logging.error(f"Ошибка при парсинге даты выдачи заказа {order[0]}: {delivery_date_str}")
                        continue
                        
                    # Для сегодняшних заказов - проверяем тип еды и время
                    meal_type = order[8]
                    if meal_type not in meal_types_to_check:
                        logging.warning(f"Заказ {idx} (индекс {order_idx}) имеет тип {meal_type}, который отсутствует в словаре meal_types_to_check")
                        continue
                        
                    # Проверяем, что для этого типа еды уже пришло время
                    if not meal_types_to_check[meal_type]:
                        logging.warning(f"Заказ {idx} (индекс {order_idx}) имеет тип {meal_type}, для которого еще не пришло время ({current_hour}:00)")
                        continue
                        
                    # Если все проверки пройдены, обновляем заказ
                    logging.info(f"Перепроверка пройдена для заказа {idx} (индекс {order_idx}). Обновляем до 'Ожидает оплаты' (сегодняшний день)")
                    orders_sheet.update(f'C{idx}', [['Ожидает оплаты']], value_input_option='USER_ENTERED')
                    logging.info(f"Заказ в строке {idx} обновлен до 'Ожидает оплаты' при запуске бота (сегодняшний день)")
                    actual_updates.append(idx)
                except Exception as e:
                    logging.error(f"Ошибка при перепроверке и обновлении заказа {idx}: {e}")
            
            logging.info(f"Обновлено {len(actual_updates)} заказов на статус 'Ожидает оплаты' при запуске бота")
        else:
            logging.info("Нет заказов, требующих обновления статуса до 'Ожидает оплаты' при запуске")
        
        return True
    except Exception as e:
        logging.error(f"Ошибка при проверке заказов на смену статуса до 'Ожидает оплаты' при запуске: {e}")
        return False

def get_credentials():
    # Получаем закодированные credentials из переменной окружения
    encoded_credentials = os.getenv('GOOGLE_CREDENTIALS_BASE64')
    if encoded_credentials:
        # Декодируем и сохраняем во временный файл
        credentials_json = base64.b64decode(encoded_credentials).decode('utf-8')
        temp_path = 'temp_credentials.json'
        with open(temp_path, 'w') as f:
            f.write(credentials_json)
        return temp_path
    return 'credentials.json'  # Для локальной разработки

# Функции авторизации
def is_user_authorized(user_id: str) -> bool:
    """Проверяет, авторизован ли пользователь по его user_id.
    
    Args:
        user_id: ID пользователя для проверки
        
    Returns:
        bool: True если пользователь авторизован, False в противном случае
    """
    try:
        # Получаем все значения из столбца C (user_id)
        user_ids = get_auth_sheet().col_values(4)
        return str(user_id) in user_ids
    except Exception as e:
        logging.error(f"Ошибка при проверке авторизации пользователя: {e}")
        return False

def check_phone(phone: str) -> bool:
    """Проверка наличия телефона в базе."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = get_auth_sheet().col_values(2)
        return phone in phones
    except Exception as e:
        logging.error(f"Ошибка при проверке телефона: {e}")
        return False

def save_user_id(phone: str, user_id: str) -> bool:
    """Сохранение user_id рядом с телефоном."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = get_auth_sheet().col_values(2)
        # Ищем индекс строки с нужным телефоном
        row_idx = phones.index(phone) + 1  # +1 потому что в gspread строки начинаются с 1
        # Обновляем ячейку с user_id (столбец C)
        get_auth_sheet().update_cell(row_idx, 4, user_id)
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении user_id: {e}")
        return False

async def force_update_menu_cache():
    """
    Принудительно обновляет кэш меню.
    
    Рекомендуется вызывать эту функцию раз в день в полночь.
    """
    _update_menu_cache(force=True)
    # Очищаем кэш функции get_dishes_for_meal, если у неё есть метод cache_clear
    if hasattr(get_dishes_for_meal, 'cache_clear'):
        get_dishes_for_meal.cache_clear()
    return True

# Кэш для составов блюд
_composition_cache = {}
_last_composition_update = None
_COMPOSITION_CACHE_TTL = 86400  # 24 часа в секундах

@profile_time
def _update_composition_cache(force=False):
    """Обновление кэша составов блюд.
    
    Args:
        force: Если True, принудительно обновляет кэш, игнорируя время последнего обновления.
    """
    global _last_composition_update
    current_time = datetime.now().timestamp()
    
    # Если кэш пустой или устарел, или требуется принудительное обновление
    if force or not _last_composition_update or (current_time - _last_composition_update) > _COMPOSITION_CACHE_TTL:
        composition_sheet = get_composition_sheet()
        
        # Получаем данные из таблицы
        all_values = composition_sheet.get_all_values()
        
        # Пропускаем заголовок
        for row in all_values[1:]:
            if row and len(row) >= 5:  # Проверяем, что строка не пустая и содержит достаточно столбцов
                dish_name = row[0].strip()
                if dish_name:  # Проверяем, что название блюда не пустое
                    composition = row[3].strip() if len(row) > 3 and row[3] else ""
                    calories = row[4].strip() if len(row) > 4 and row[4] else ""
                    _composition_cache[dish_name] = {
                        "composition": composition,
                        "calories": calories
                    }
        
        _last_composition_update = current_time
        logging.info(f"Кэш составов блюд обновлен в {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")

def get_dish_composition(dish_name):
    """Получение состава и калорийности блюда по его названию.
    
    Args:
        dish_name: Название блюда
        
    Returns:
        dict: Словарь с составом и калорийностью блюда, или пустой словарь если блюдо не найдено
    """
    _update_composition_cache()
    return _composition_cache.get(dish_name.strip(), {"composition": "", "calories": ""})

async def force_update_composition_cache():
    """Принудительно обновляет кэш составов блюд.
    
    Рекомендуется вызывать эту функцию вместе с обновлением кэша меню.
    """
    _update_composition_cache(force=True)
    # В текущем коде get_dish_composition не использует декоратор lru_cache
    # Проверку на наличие cache_clear оставляем для будущей совместимости
    return True

# Кэш для меню на сегодня
_today_menu_cache = {}
_last_today_menu_update = None
_TODAY_MENU_CACHE_TTL = 86400  # 24 часа в секундах

@profile_time
def _update_today_menu_cache(force=False):
    """Обновление кэша меню на сегодня.
    
    Args:
        force: Если True, принудительно обновляет кэш, игнорируя время последнего обновления.
    """
    global _last_today_menu_update, _today_menu_cache
    current_time = datetime.now().timestamp()
    
    # Если кэш пустой или устарел, или требуется принудительное обновление
    if force or not _last_today_menu_update or (current_time - _last_today_menu_update) > _TODAY_MENU_CACHE_TTL:
        try:
            # Получаем листа с меню на сегодня
            menu_sheet = client.open_by_key(config.MENU_SPREADSHEET_ID).get_worksheet_by_id(TODAY_MENU_SHEET_ID)
            
            if not menu_sheet:
                logging.error("Не удалось получить лист с меню на сегодня")
                return
                
            # Получаем текущую дату в формате дд.мм.гг
            today = datetime.now().strftime("%d.%m.%y")
            
            # Получаем все строки из листа
            rows = menu_sheet.get_all_values()
            
            # Ищем строку с сегодняшней датой
            today_menu_row = None
            for row in rows:
                if row and row[0].strip() == today:
                    today_menu_row = row
                    break
            
            if today_menu_row:
                # Получаем названия блюд из диапазона колонок с 3 по 41
                all_dishes = [dish.strip() for dish in today_menu_row[2:41] if dish.strip()]
                
                # Группируем блюда по типам приема пищи
                grouped_dishes = {
                    'Завтрак': [],
                    'Обед': [],
                    'Ужин': []
                }
                
                current_meal_type = None
                
                for dish in all_dishes:
                    # Проверяем, является ли элемент названием типа приема пищи
                    if dish in ['Завтрак', 'Обед', 'Ужин']:
                        current_meal_type = dish
                    elif current_meal_type and dish:
                        # Добавляем блюдо к текущему типу приема пищи
                        grouped_dishes[current_meal_type].append(dish)
                
                _today_menu_cache["dishes"] = grouped_dishes
                _last_today_menu_update = current_time
                logging.info(f"Кэш меню на сегодня обновлен в {datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                logging.info(f"Меню на сегодня ({today}) не найдено в таблице")
                _today_menu_cache["dishes"] = {'Завтрак': [], 'Обед': [], 'Ужин': []}
                _last_today_menu_update = current_time
        except Exception as e:
            logging.error(f"Ошибка при обновлении кэша меню на сегодня: {e}")

def get_today_menu_dishes():
    """Получение списка блюд из меню на сегодня, сгруппированных по типам приема пищи.
    
    Returns:
        Dict[str, List[str]]: Словарь с ключами 'Завтрак', 'Обед', 'Ужин' и списками блюд
    """
    _update_today_menu_cache()
    return _today_menu_cache.get("dishes", {'Завтрак': [], 'Обед': [], 'Ужин': []})

async def force_update_today_menu_cache():
    """Принудительно обновляет кэш меню на сегодня."""
    _update_today_menu_cache(force=True)
    # В текущем коде get_today_menu_dishes не использует декоратор lru_cache
    # Проверку на наличие cache_clear оставляем для будущей совместимости
    return True

def get_admins_ids() -> List[str]:
    """Получение списка ID администраторов.
    
    Returns:
        List[str]: Список ID администраторов
    """
    try:
        # Пропускаем заголовок и берем первый столбец
        return get_admins_sheet().col_values(1)[1:]
    except Exception as e:
        logging.error(f"Ошибка при получении списка администраторов: {e}")
        return []



@profile_time
def get_payments_sheet():
    """Получение листа оплат."""
    try:
        return spreadsheet.get_worksheet_by_id(PAYMENTS_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Payments", 1000, 7)
        sheet.update('A1:G1', [['Номер оплаты', 'Дата и время', 'User ID', 'Комментарий', 'Сумма', 'Статус', 'Номер комнаты']])
        return sheet

def get_next_payment_id() -> str:
    """Получение следующего номера оплаты.
    
    Returns:
        str: Следующий доступный номер оплаты
    """
    try:
        payments_sheet = get_payments_sheet()
        all_payments = payments_sheet.get_all_values()
        
        # Если в таблице только заголовок или она пуста
        if len(all_payments) <= 1:
            return "1"
            
        # Получаем все номера оплат из первого столбца (пропускаем заголовок)
        payment_ids = [int(row[0]) for row in all_payments[1:] if row[0].isdigit()]
        
        # Если нет ни одного номера, начинаем с 1
        if not payment_ids:
            return "1"
            
        # Возвращаем следующий номер
        return str(max(payment_ids) + 1)
    except Exception as e:
        logging.error(f"Ошибка при получении следующего номера оплаты: {e}")
        return "1"

async def save_payment_info(user_id: str, amount: float, status: str = "ожидает", room: str = "") -> bool:
    """Сохранение информации об оплате в таблицу.
    
    Args:
        user_id: ID пользователя
        amount: Сумма оплаты
        status: Статус оплаты (ожидает, оплачено, отменено, отклонено)
        room: Номер комнаты пользователя
        
    Returns:
        bool: True в случае успешного сохранения, False в противном случае
    """
    try:
        # Получаем следующий номер оплаты
        next_id = get_next_payment_id()
        
        # Форматируем текущую дату и время
        now = datetime.now()
        formatted_datetime = now.strftime("%d.%m.%y %H:%M:%S")
        
        # Получаем таблицу платежей
        payments_sheet = get_payments_sheet()
        
        # Находим первую пустую строку
        all_payments = payments_sheet.get_all_values()
        next_row_index = len(all_payments) + 1
        
        # Обновляем каждую ячейку отдельно, пропуская колонку комментария (D)
        payments_sheet.update_cell(next_row_index, 1, next_id)  # A - Номер оплаты
        payments_sheet.update_cell(next_row_index, 2, formatted_datetime)  # B - Дата и время
        payments_sheet.update_cell(next_row_index, 3, user_id)  # C - User ID
        # Колонку D (Комментарий) не трогаем
        payments_sheet.update_cell(next_row_index, 5, str(amount))  # E - Сумма оплаты
        payments_sheet.update_cell(next_row_index, 6, status)  # F - Статус оплаты
        payments_sheet.update_cell(next_row_index, 7, room)  # G - Номер комнаты
        
        logging.info(f"Информация об оплате {next_id} сохранена в таблицу")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при сохранении информации об оплате: {e}")
        return False

async def save_question(user_id: str, question_text: str) -> bool:
    """Сохранение вопроса в таблицу.
    
    Args:
        user_id: ID пользователя, задавшего вопрос
        question_text: Текст вопроса
        
    Returns:
        bool: True в случае успешного сохранения, False в противном случае
    """
    try:
        # Получаем информацию о пользователе
        username = '-'
        profile_link = '-'
        phone = '-'
        
        # Находим пользователя в таблице Users
        users_data = get_users_sheet().get_all_values()
        for row in users_data[1:]:  # Пропускаем заголовок
            if row[0] == user_id:
                profile_link = row[1]  # Profile Link
                phone = row[3]  # Phone Number
                break
        
        # Форматируем дату и время
        now = datetime.now()
        formatted_date = now.strftime("%d.%m.%Y %H:%M:%S")
        
        # Сохраняем вопрос
        questions_sheet = get_questions_sheet()
        questions_sheet.append_row([
            formatted_date,  # Дата и время
            profile_link,    # Ссылка на пользователя
            phone,           # Телефон
            question_text    # Текст вопроса
        ], value_input_option='USER_ENTERED')
        
        logging.info(f"Вопрос от пользователя {user_id} сохранен в таблицу")
        return True
    except Exception as e:
        logging.error(f"Ошибка при сохранении вопроса: {e}")
        return False

# Инициализация листов
orders_sheet = get_orders_sheet()
users_sheet = get_users_sheet()
rec_sheet = get_rec_sheet()
auth_sheet = get_auth_sheet()