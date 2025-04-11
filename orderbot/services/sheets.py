import gspread
from .. import config
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from functools import lru_cache
import base64
import json
import os

# Подключаемся к Google Sheets
client = gspread.service_account(filename=config.GOOGLE_CREDENTIALS_FILE)

# Открываем таблицу заказов
spreadsheet = client.open(config.ORDERS_SHEET_NAME)

# ID листов
ORDERS_SHEET_ID = 2082646960
USERS_SHEET_ID = 505696272
KITCHEN_SHEET_ID = 2090492372
REC_SHEET_ID = 1331625926
AUTH_SHEET_ID = 66851994
MENU_SHEET_ID = 1808438200

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

def get_users_sheet():
    """Получение листа пользователей."""
    try:
        print(f"Пытаемся получить лист пользователей по ID: {USERS_SHEET_ID}")
        sheet = spreadsheet.get_worksheet_by_id(USERS_SHEET_ID)
        print(f"Успешно получен лист: {sheet.title}")
        return sheet
    except gspread.WorksheetNotFound as e:
        print(f"Лист не найден: {e}")
        print("Создаем новый лист Users")
        sheet = spreadsheet.add_worksheet("Users", 1000, 10)
        sheet.update('A1:J1', [['User ID', 'Profile Link', 'First Name', 
                              'Last Name', 'Phone Number', 'Start Time',
                              'Orders Count', 'Cancellations', 
                              'Total Sum', 'Last Order Date']])
        return sheet
    except Exception as e:
        print(f"Неожиданная ошибка при получении листа пользователей: {e}")
        raise

def get_kitchen_sheet():
    """Получение листа кухни."""
    try:
        return spreadsheet.get_worksheet_by_id(KITCHEN_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Kitchen", 100, 1)
        sheet.update('A1', [['User ID']])
        return sheet

def get_rec_sheet():
    """Получение листа записей."""
    try:
        return spreadsheet.get_worksheet_by_id(REC_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Rec", 1000, 6)
        sheet.update('A1:F1', [['Дата', 'Количество заказов', 'Общая сумма', 
                              'Средний чек', 'Количество отмен', 'Процент отмен']])
        return sheet

def get_auth_sheet():
    """Получение листа авторизации."""
    try:
        return spreadsheet.get_worksheet_by_id(AUTH_SHEET_ID)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("Auth", 1000, 2)
        sheet.update('A1:B1', [['Phone Number', 'User ID']])
        return sheet

def get_menu_sheet():
    """Получение листа меню."""
    return client.open(config.MENU_SHEET_NAME).get_worksheet_by_id(MENU_SHEET_ID)

# Кэш для меню
_menu_cache: Dict[str, List[Tuple[str, str]]] = {}
_last_menu_update = None
_MENU_CACHE_TTL = 300  # 5 минут в секундах

def _update_menu_cache():
    """Обновление кэша меню."""
    global _last_menu_update
    current_time = datetime.now().timestamp()
    
    # Если кэш пустой или устарел, обновляем его
    if not _last_menu_update or (current_time - _last_menu_update) > _MENU_CACHE_TTL:
        column_map = {
            'breakfast': (1, 2),  # A и B столбцы
            'lunch': (3, 4),      # C и D столбцы
            'dinner': (5, 6)      # E и F столбцы
        }
        
        menu_sheet = get_menu_sheet()
        for meal_type, (dish_col, price_col) in column_map.items():
            dishes = menu_sheet.col_values(dish_col)[1:]
            prices = menu_sheet.col_values(price_col)[1:]
            _menu_cache[meal_type] = list(zip(dishes, prices))
        
        _last_menu_update = current_time

@lru_cache(maxsize=100)
def get_dishes_for_meal(meal_type: str) -> List[Tuple[str, str]]:
    """Получение списка блюд с ценами для выбранного типа еды."""
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
        print(f"Ошибка при сохранении заказа: {e}")
        return False

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
        print(f"Ошибка при обновлении заказа: {e}")
        return False

async def get_user_orders(user_id: str) -> List[List[str]]:
    """Получение всех активных заказов пользователя."""
    try:
        all_orders = get_orders_sheet().get_all_values()
        return [row for row in all_orders[1:] if row[3] == user_id and row[2] == 'Активен']
    except Exception as e:
        print(f"Ошибка при получении заказов пользователя: {e}")
        return []

async def update_order_status(order_id: str, row_idx: int, status: str) -> bool:
    """Обновление статуса заказа."""
    try:
        get_orders_sheet().update_cell(row_idx, 3, status)  # Колонка C содержит статус
        return True
    except Exception as e:
        print(f"Ошибка при обновлении статуса заказа: {e}")
        return False

async def save_user_info(user_info: dict):
    """Сохранение информации о пользователе."""
    try:
        user_id = user_info['user_id']
        username = user_info.get('username', '-')
        profile_link = f"t.me/{username}" if username != '-' else '-'
        
        print(f"Сохраняем информацию о пользователе {user_id}")
        
        # Проверяем, существует ли пользователь
        users_sheet = get_users_sheet()
        users_data = users_sheet.get_all_values()
        print(f"Получено {len(users_data)} строк из листа пользователей")
        
        user_exists = False
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                print(f"Найден существующий пользователь в строке {idx + 1}")
                # Обновляем существующего пользователя
                users_sheet.update(f'A{idx+1}:C{idx+1}', 
                                 [[user_id, profile_link, username]],
                                 value_input_option='USER_ENTERED')
                user_exists = True
                print("Информация о пользователе обновлена")
                break
        
        if not user_exists:
            print("Создаем новую запись о пользователе")
            # Добавляем нового пользователя
            new_user_row = [
                user_id,
                profile_link,
                username,
                '-',  # First Name
                '-',  # Last Name
                '',   # Phone Number
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Start Time
                '0',  # Orders Count
                '0',  # Cancellations
                '0',  # Total Sum
                ''    # Last Order Date
            ]
            users_sheet.append_row(new_user_row, value_input_option='USER_ENTERED')
            print("Новый пользователь добавлен")
        
        return True
    except Exception as e:
        print(f"Ошибка при сохранении информации о пользователе: {e}")
        return False

async def update_user_stats(user_id: str):
    """Обновление статистики пользователя."""
    try:
        # Получаем все заказы
        all_orders = get_orders_sheet().get_all_values()
        
        # Подсчитываем статистику пользователя
        active_orders = 0
        cancelled_orders = 0
        total_sum = 0
        last_order_date = None
        
        for order in all_orders[1:]:  # Пропускаем заголовок
            if order[3] == user_id:  # User ID в четвертом столбце
                try:
                    # Парсим дату из формата DD.MM.YYYY HH:MM:SS
                    order_date = datetime.strptime(order[1], "%d.%m.%Y %H:%M:%S")
                    # Сравниваем даты как объекты datetime
                    if last_order_date is None or order_date > last_order_date:
                        last_order_date = order_date
                        print(f"Найден более новый заказ: {order_date.strftime('%d.%m.%Y %H:%M:%S')}")
                except ValueError:
                    print(f"Ошибка парсинга даты заказа: {order[1]}")
                    continue
                
                if order[2] == 'Активен':  # Статус в третьем столбце
                    active_orders += 1
                    total_sum += float(order[5]) if order[5] else 0  # Сумма в шестом столбце
                elif order[2] == 'Отменён':
                    cancelled_orders += 1
        
        # Получаем текущие данные пользователя
        users_sheet = get_users_sheet()
        users_data = users_sheet.get_all_values()
        user_row = None
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                user_row = idx + 1
                break
        
        if user_row:
            # Форматируем дату последнего заказа
            formatted_date = last_order_date.strftime("%d.%m.%Y %H:%M:%S") if last_order_date else ''
            
            # Обновляем статистику пользователя
            # F-I столбцы (индексы 5-8): Orders Count, Cancellations, Total Sum, Last Order Date
            users_sheet.update(f'F{user_row}:I{user_row}', 
                             [[str(active_orders), 
                               str(cancelled_orders), 
                               str(int(total_sum)),
                               formatted_date]],
                             value_input_option='USER_ENTERED')
            print(f"Обновлена статистика пользователя {user_id}: {active_orders} активных заказов, {cancelled_orders} отмен, сумма {total_sum}, последний заказ {formatted_date}")
        
        return True
    except Exception as e:
        print(f"Ошибка при обновлении статистики пользователя: {e}")
        return False

async def get_user_stats(user_id: str):
    """Получение статистики пользователя."""
    try:
        users_data = get_users_sheet().get_all_values()
        for row in users_data[1:]:  # Пропускаем заголовок
            if row[0] == user_id:
                return {
                    'orders_count': int(row[3]),
                    'cancellations': int(row[4]),
                    'total_sum': int(float(row[5])),
                    'last_order_date': row[6]
                }
        return None
    except Exception as e:
        print(f"Ошибка при получении статистики пользователя: {e}")
        return None

def is_user_cook(user_id: str) -> bool:
    """Проверяет, является ли пользователь поваром."""
    try:
        # Получаем все ID поваров из первого столбца
        cook_ids = get_kitchen_sheet().col_values(1)
        return str(user_id) in cook_ids
    except Exception as e:
        print(f"Ошибка при проверке доступа повара: {e}")
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
        all_orders = get_orders_sheet().get_all_values()
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
                        print(f"Ошибка при парсинге даты выдачи заказа {order[0]}: {delivery_date_str}")
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
                get_orders_sheet().update(range_name, values, value_input_option='USER_ENTERED')
        
        return True
    except Exception as e:
        print(f"Ошибка при обновлении статусов заказов: {e}")
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
        # Получаем все значения из столбца B (user_id)
        user_ids = get_auth_sheet().col_values(2)
        return str(user_id) in user_ids
    except Exception as e:
        print(f"Ошибка при проверке авторизации пользователя: {e}")
        return False

def check_phone(phone: str) -> bool:
    """Проверка наличия телефона в базе."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = get_auth_sheet().col_values(1)
        return phone in phones
    except Exception as e:
        print(f"Ошибка при проверке телефона: {e}")
        return False

def save_user_id(phone: str, user_id: str) -> bool:
    """Сохранение user_id рядом с телефоном."""
    try:
        # Получаем все значения из столбца A (телефоны)
        phones = get_auth_sheet().col_values(1)
        # Ищем индекс строки с нужным телефоном
        row_idx = phones.index(phone) + 1  # +1 потому что в gspread строки начинаются с 1
        # Обновляем ячейку с user_id (столбец B)
        get_auth_sheet().update_cell(row_idx, 2, user_id)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении user_id: {e}")
        return False

# Инициализация листов
orders_sheet = get_orders_sheet()
users_sheet = get_users_sheet()
rec_sheet = get_rec_sheet()
auth_sheet = get_auth_sheet()