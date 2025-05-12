import gspread
from .. import config
from .sheets import client, orders_sheet, users_sheet, auth_sheet
from datetime import datetime
import logging

async def update_user_info(user):
    """Обновление информации о пользователе."""
    user_id = str(user.id).strip("'")  # Убираем апострофы, если они есть
    username = user.username or '-'
    profile_link = f"t.me/{username}" if username != '-' else '-'
    first_name = user.first_name or '-'
    last_name = user.last_name or '-'
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # Получаем все записи о пользователях
        all_users = users_sheet.get_all_values()
        
        # Если лист пустой, добавляем заголовки
        if not all_users:
            users_sheet.append_row([
                'User ID',
                'Profile Link',
                'First Name',
                'Last Name',
                'Phone Number',
                'Room Number',  # Был Start Time, теперь Room Number
                'Orders Count',
                'Cancellations',
                'Total Sum',
                'Unpaid Sum',   # Новый столбец: сумма неоплаченных заказов
                'Start Time',   # Перемещен с 6-й позиции на 11-ю
                'Last Order Date'  # Перемещен с 10-й на 12-ю
            ], value_input_option='USER_ENTERED')
            all_users = users_sheet.get_all_values()
        
        # Получаем номер телефона из таблицы Auth
        phone = ''
        try:
            # Получаем все значения из столбцов таблицы Auth
            auth_data = auth_sheet.get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                    phone = row[1]  # Берем номер телефона из второго столбца
                    break
        except Exception as e:
            logging.error(f"Ошибка при получении номера телефона из таблицы Auth: {e}")
        
        user_found = False
        
        # Ищем пользователя и обновляем информацию
        for idx, row in enumerate(all_users[1:], start=2):  # Пропускаем заголовок
            if row[0] == user_id:
                # Обновляем основную информацию о пользователе, сохраняя текущее значение Room Number
                # Внимание: мы не обновляем всю строку A:F, поскольку 6-я колонка теперь Room Number
                users_sheet.update(f'A{idx}:E{idx}', 
                                [[user_id, profile_link, first_name, last_name, phone]],
                                value_input_option='USER_ENTERED')
                
                # Проверяем и обновляем Start Time, только если оно не установлено
                if not row[10] or row[10] == '':  # Индекс 10 - Start Time
                    users_sheet.update_cell(idx, 11, start_time)  # Колонка K (11) - Start Time
                
                user_found = True
                break
        
        # Если пользователь не найден, добавляем новую запись
        if not user_found:
            next_row = len(all_users) + 1
            new_user_row = [
                user_id,
                profile_link,
                first_name,
                last_name,
                phone,       # Phone Number из таблицы Auth
                '',          # Room Number (пустое)
                '0',         # Orders Count
                '0',         # Cancellations
                '0',         # Total Sum
                '0',         # Unpaid Sum
                start_time,  # Start Time
                ''           # Last Order Date
            ]
            # Используем явное указание диапазона вместо append_row
            users_sheet.update(f'A{next_row}:L{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новая запись о пользователе добавлена в строку {next_row}")
            
        if user_found:
            logging.info(f"Обновлена информация о пользователе {user.id} в таблице Users")
        else:
            logging.info(f"Создана новая запись о пользователе {user.id} в таблице Users")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении информации о пользователе: {e}")
        return False

async def update_user_totals():
    """Обновление общей суммы заказов пользователей."""
    # Получаем все заказы
    all_orders = orders_sheet.get_all_values()
    
    # Создаем словарь для хранения сумм по пользователям
    user_totals = {}
    user_unpaid = {}  # Новый словарь для неоплаченных сумм
    
    # Подсчитываем суммы активных заказов для каждого пользователя
    for order in all_orders[1:]:  # Пропускаем заголовок
        if order[2] in ['Активен', 'Принят', 'Ожидает оплаты', 'Оплачен']:  # Проверяем статус заказа
            user_id = order[3]
            try:
                amount = float(order[5]) if order[5] else 0
                
                # Общая сумма заказов
                if user_id not in user_totals:
                    user_totals[user_id] = 0
                user_totals[user_id] += amount
                
                # Сумма неоплаченных заказов (все кроме оплаченных)
                if order[2] in ['Активен', 'Принят', 'Ожидает оплаты']:
                    if user_id not in user_unpaid:
                        user_unpaid[user_id] = 0
                    user_unpaid[user_id] += amount
                
            except (ValueError, IndexError) as e:
                logging.error(f"Ошибка при обработке суммы заказа: {e}")
                continue
    
    # Получаем все записи о пользователях
    all_users = users_sheet.get_all_values()
    
    # Обновляем суммы в таблице пользователей
    for idx, row in enumerate(all_users[1:], start=2):  # Начинаем с 2, так как пропускаем заголовок
        user_id = row[0]
        total = user_totals.get(user_id, 0)
        unpaid = user_unpaid.get(user_id, 0)
        
        # Обновляем общую сумму заказов
        users_sheet.update_cell(idx, 9, str(int(total)))  # Обновляем столбец I (9) - Total Sum
        
        # Обновляем сумму неоплаченных заказов
        users_sheet.update_cell(idx, 10, str(int(unpaid)))  # Обновляем столбец J (10) - Unpaid Sum

async def update_user_stats(user_id: str):
    """Обновление статистики пользователя."""
    try:
        # Получаем все заказы
        all_orders = orders_sheet.get_all_values()
        
        # Подсчитываем статистику пользователя
        active_orders = 0
        cancelled_orders = 0
        total_sum = 0
        unpaid_sum = 0  # Новая переменная для суммы неоплаченных заказов
        last_order_date = None
        
        # Создаем словарь для подсчета статусов
        status_counts = {}
        
        for order in all_orders[1:]:  # Пропускаем заголовок
            if order[3] == user_id:  # User ID в четвертом столбце
                try:
                    # Парсим дату в формате DD.MM.YYYY HH:MM:SS
                    order_date = datetime.strptime(order[1], "%d.%m.%Y %H:%M:%S")
                    logging.info(f"Обработка заказа от {order_date} для пользователя {user_id}")
                    
                    if last_order_date is None or order_date > last_order_date:
                        logging.info(f"Найден более новый заказ: {order_date} (было {last_order_date})")
                        last_order_date = order_date
                except ValueError as e:
                    logging.error(f"Ошибка при парсинге даты заказа {order[1]}: {e}")
                    continue
                
                # Получаем статус и убираем лишние пробелы
                status = order[2].strip()
                logging.info(f"Заказ {order[0]}: статус = '{status}'")
                
                # Подсчитываем количество каждого статуса
                status_counts[status] = status_counts.get(status, 0) + 1
                
                # Проверяем статус заказа
                if status in ['Активен', 'Принят', 'Ожидает оплаты', 'Оплачен']:
                    active_orders += 1
                    order_sum = float(order[5]) if order[5] else 0  # Сумма в шестом столбце
                    total_sum += order_sum
                    
                    # Учитываем неоплаченные заказы
                    if status in ['Активен', 'Принят', 'Ожидает оплаты']:
                        unpaid_sum += order_sum
                        
                    logging.info(f"Заказ {order[0]} со статусом '{status}' учтен в активных заказах")
                elif status == 'Отменён':
                    cancelled_orders += 1
                    logging.info(f"Заказ {order[0]} со статусом '{status}' учтен в отмененных заказах")
                else:
                    logging.info(f"Заказ {order[0]} со статусом '{status}' НЕ учтен (неизвестный статус)")
        
        # Логируем статистику по статусам
        logging.info(f"Статистика по статусам заказов для пользователя {user_id}:")
        for status, count in status_counts.items():
            logging.info(f"Статус '{status}': {count} заказов")
        
        # Дополнительно логируем информацию о неоплаченных заказах
        logging.info(f"Общая сумма неоплаченных заказов для пользователя {user_id}: {unpaid_sum} р.")
        
        # Получаем текущие данные пользователя
        users_data = users_sheet.get_all_values()
        user_row = None
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                user_row = idx + 1
                break
        
        if user_row:
            # Форматируем дату для сохранения в том же формате DD.MM.YYYY HH:MM:SS
            formatted_date = last_order_date.strftime("%d.%m.%Y %H:%M:%S") if last_order_date else ''
            logging.info(f"Обновление статистики для пользователя {user_id}: активных заказов {active_orders}, отмен {cancelled_orders}, общая сумма {total_sum}, неоплаченная сумма {unpaid_sum}, последний заказ {formatted_date}")
            
            # Обновляем статистику 
            # G-K: Orders Count, Cancellations, Total Sum, Unpaid Sum, Last Order Date (переместилась с J на L)
            users_sheet.update(f'G{user_row}:J{user_row}', 
                             [[str(active_orders), 
                               str(cancelled_orders), 
                               str(int(total_sum)),
                               str(int(unpaid_sum))]],  # Добавляем неоплаченную сумму
                             value_input_option='USER_ENTERED')
            
            # Отдельно обновляем дату последнего заказа (теперь в столбце L)
            if formatted_date:
                users_sheet.update_cell(user_row, 12, formatted_date)
        
        logging.info(f"Обновлена статистика пользователей в таблице Users")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статистики пользователя: {e}")
        return False

async def update_user_info_by_id(user_id: str):
    """Создание базовой записи о пользователе по ID."""
    try:
        # Получаем информацию о пользователе из заказов
        all_orders = orders_sheet.get_all_values()
        user_orders = [order for order in all_orders[1:] if order[3] == user_id]
        
        if user_orders:
            latest_order = user_orders[-1]
            username = latest_order[4]  # Username в пятом столбце
            profile_link = f"t.me/{username}" if username and username != '-' else '-'
            
            # Для номера комнаты берем данные из последнего заказа, если они есть
            room_number = latest_order[6] if len(latest_order) > 6 else ''  # Room в седьмом столбце
            
            # Получаем все записи пользователей
            users_data = users_sheet.get_all_values()
            next_row = len(users_data) + 1
            
            # Добавляем базовую запись с новой структурой
            new_user_row = [
                user_id,
                profile_link,
                '-',         # First Name
                '-',         # Last Name
                '',          # Phone Number
                room_number, # Room Number (новое поле)
                '0',         # Orders Count
                '0',         # Cancellations
                '0',         # Total Sum
                '0',         # Unpaid Sum (новое поле)
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Start Time
                ''           # Last Order Date
            ]
            # Используем явное указание диапазона вместо append_row
            users_sheet.update(f'A{next_row}:L{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новая базовая запись о пользователе {user_id} добавлена в строку {next_row}")
            
            # Сразу обновляем статистику
            await update_user_stats(user_id)
            
            logging.info(f"Создана новая запись о пользователе {user_id} в таблице Users")
            return True
        return False
    except Exception as e:
        logging.error(f"Ошибка при создании записи о пользователе: {e}")
        return False

async def save_user_phone(user_id: str, phone: str):
    """Сохранение номера телефона пользователя."""
    try:
        users_data = users_sheet.get_all_values()
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                # Обновляем номер телефона (столбец E) - индекс не меняется
                users_sheet.update(f'E{idx + 1}', [[phone]], value_input_option='USER_ENTERED')
                logging.info(f"Сохранен номер телефона для пользователя {user_id} в таблице Auth")
                return True
        return False
    except Exception as e:
        logging.error(f"Ошибка при сохранении номера телефона: {e}")
        return False

async def create_user_record(user_id: int, username: str, first_name: str, last_name: str) -> bool:
    try:
        # ... existing code ...
        logging.info(f"Создана новая запись о пользователе {user_id} в таблице Users")
        return True
    except Exception as e:
        logging.error(f"Ошибка при создании записи о пользователе: {e}")
        return False 