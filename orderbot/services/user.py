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
                'Phone Number',
                'Room Number',
                'Orders Count',
                'Cancellations',
                'Total Sum',
                'Unpaid Sum',
                'Start Time',
                'Last Order Date'
            ], value_input_option='USER_ENTERED')
            all_users = users_sheet.get_all_values()
        
        # Получаем имя, номер телефона и номер комнаты из таблицы Auth
        auth_name = '-'
        phone = ''
        room_number = ''
        try:
            # Получаем все значения из столбцов таблицы Auth
            auth_data = auth_sheet.get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                    auth_name = row[0] or '-'  # Берем имя из первого столбца
                    phone = row[1]  # Берем номер телефона из второго столбца
                    if len(row) >= 3 and row[2]:  # Проверяем наличие номера комнаты
                        room_number = row[2]  # Берем номер комнаты из третьего столбца
                    break
        except Exception as e:
            logging.error(f"Ошибка при получении данных из таблицы Auth: {e}")
        
        user_found = False
        
        # Ищем пользователя и обновляем информацию
        for idx, row in enumerate(all_users[1:], start=2):  # Пропускаем заголовок
            if row[0] == user_id:
                # Обновляем основную информацию о пользователе, сохраняя текущее значение Room Number
                users_sheet.update(f'A{idx}:D{idx}', 
                                [[user_id, profile_link, auth_name, phone]],
                                value_input_option='USER_ENTERED')
                
                # Обновляем номер комнаты из таблицы Auth, если он есть
                if room_number:
                    users_sheet.update_cell(idx, 5, room_number)  # Колонка E (5) - Room Number (сдвинуто влево)
                    logging.info(f"Номер комнаты {room_number} обновлен для пользователя {user.id}")
                
                # Проверяем и обновляем Start Time, только если оно не установлено
                if not row[9] or row[9] == '':  # Индекс 9 - Start Time (сдвинуто влево)
                    users_sheet.update_cell(idx, 10, start_time)  # Колонка J (10) - Start Time (сдвинуто влево)
                
                user_found = True
                break
        
        # Если пользователь не найден, добавляем новую запись
        if not user_found:
            next_row = len(all_users) + 1
            new_user_row = [
                user_id,
                profile_link,
                auth_name,      # Имя из таблицы Auth вместо first_name
                phone,          # Phone Number из таблицы Auth
                room_number,    # Room Number из таблицы Auth
                '0',            # Orders Count
                '0',            # Cancellations
                '0',            # Total Sum
                '0',            # Unpaid Sum
                start_time,     # Start Time
                ''              # Last Order Date
            ]
            # Используем явное указание диапазона вместо append_row
            users_sheet.update(f'A{next_row}:K{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новая запись о пользователе добавлена в строку {next_row}")
            if room_number:
                logging.info(f"Номер комнаты {room_number} сохранен для нового пользователя {user.id}")
            
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
        users_sheet.update_cell(idx, 8, str(int(total)))  # Обновляем столбец H (8) - Total Sum (сдвинуто влево)
        
        # Обновляем сумму неоплаченных заказов
        users_sheet.update_cell(idx, 9, str(int(unpaid)))  # Обновляем столбец I (9) - Unpaid Sum (сдвинуто влево)

async def update_user_stats(user_id: str):
    """Обновление статистики пользователя."""
    try:
        # Логирование входных параметров
        logging.info(f"Вызов update_user_stats с user_id: '{user_id}', тип: {type(user_id)}")
        
        # Получаем все заказы
        all_orders = orders_sheet.get_all_values()
        logging.info(f"Получено {len(all_orders)-1} заказов (без учета заголовка)")
        
        # Подсчитываем статистику пользователя
        active_orders = 0
        cancelled_orders = 0
        total_sum = 0
        unpaid_sum = 0  # Новая переменная для суммы неоплаченных заказов
        last_order_date = None
        
        # Создаем словарь для подсчета статусов
        status_counts = {}
        
        # Подсчитываем заказы пользователя
        user_orders_count = 0
        for order in all_orders[1:]:  # Пропускаем заголовок
            if order[3] == user_id:  # User ID в четвертом столбце
                user_orders_count += 1
        
        logging.info(f"Найдено {user_orders_count} заказов для пользователя {user_id}")
        
        for order in all_orders[1:]:  # Пропускаем заголовок
            order_user_id = order[3]
            # Логируем информацию для отладки
            if order_user_id == user_id:
                logging.info(f"Найден заказ для user_id={user_id}: ID заказа={order[0]}, статус={order[2]}")
            
            if order_user_id == user_id:  # User ID в четвертом столбце
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
        
        # Если у пользователя нет заказов, возможно его ID некорректный
        if user_orders_count == 0:
            logging.warning(f"Для пользователя с ID '{user_id}' не найдено ни одного заказа")
        
        # Логируем статистику по статусам
        logging.info(f"Статистика по статусам заказов для пользователя {user_id}:")
        for status, count in status_counts.items():
            logging.info(f"Статус '{status}': {count} заказов")
        
        # Дополнительно логируем информацию о неоплаченных заказах
        logging.info(f"Общая сумма неоплаченных заказов для пользователя {user_id}: {unpaid_sum} р.")
        
        # Получаем текущие данные пользователя
        users_data = users_sheet.get_all_values()
        logging.info(f"Получено {len(users_data)-1} записей пользователей (без учета заголовка)")
        
        # Ищем пользователя по ID
        user_row = None
        for idx, row in enumerate(users_data):
            row_user_id = row[0]
            logging.info(f"Проверка строки {idx+1}: user_id='{row_user_id}', тип={type(row_user_id)}, сравнение с '{user_id}' = {row_user_id == user_id}")
            if row_user_id == user_id:
                user_row = idx + 1
                logging.info(f"Найден пользователь в строке {user_row}")
                break
        
        # Если пользователь не найден, создаем новую запись
        if not user_row:
            logging.warning(f"Пользователь с ID '{user_id}' не найден в таблице Users")
            
            # Попытка получить данные пользователя из заказов
            username = '-'
            profile_link = '-'
            
            # Ищем имя пользователя в заказах
            for order in all_orders[1:]:
                if order[3] == user_id:
                    username = order[4] or '-'  # Username в пятом столбце
                    break
            
            # Проверяем наличие имени пользователя в auth_sheet
            auth_name = '-'
            room_number = ''
            try:
                auth_data = auth_sheet.get_all_values()
                for row in auth_data[1:]:  # Пропускаем заголовок
                    if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                        auth_name = row[0] or '-'  # Берем имя из первого столбца
                        if len(row) >= 3 and row[2]:  # Проверяем наличие номера комнаты
                            room_number = row[2]  # Берем номер комнаты из третьего столбца
                        break
            except Exception as e:
                logging.error(f"Ошибка при получении данных из таблицы Auth: {e}")
            
            # Формируем profile_link, если есть username
            if username != '-':
                profile_link = f"t.me/{username}"
            
            logging.info(f"Создаем новую запись для пользователя {user_id} с именем {auth_name} и комнатой {room_number}")
            
            # Добавляем новую запись пользователя
            next_row = len(users_data) + 1
            new_user_row = [
                user_id,
                profile_link,
                auth_name,      # Имя из таблицы Auth
                '',             # Phone Number
                room_number,    # Room Number
                str(active_orders),  # Orders Count - сразу заполняем текущими значениями
                str(cancelled_orders),  # Cancellations
                str(int(total_sum)),  # Total Sum
                str(int(unpaid_sum)),  # Unpaid Sum
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Start Time
                last_order_date.strftime("%d.%m.%Y %H:%M:%S") if last_order_date else ''  # Last Order Date
            ]
            
            # Используем явное указание диапазона для добавления новой строки
            users_sheet.update(f'A{next_row}:K{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новый пользователь {user_id} добавлен в строку {next_row} со статистикой: активных заказов {active_orders}, отмен {cancelled_orders}, сумма {total_sum}, неоплаченная сумма {unpaid_sum}")
            
            # Успешно обновили через создание новой записи
            return True
        
        # Пользователь найден, обновляем его данные
        if user_row:
            # Форматируем дату для сохранения в том же формате DD.MM.YYYY HH:MM:SS
            formatted_date = last_order_date.strftime("%d.%m.%Y %H:%M:%S") if last_order_date else ''
            logging.info(f"Обновление статистики для пользователя {user_id} в строке {user_row}: активных заказов {active_orders}, отмен {cancelled_orders}, общая сумма {total_sum}, неоплаченная сумма {unpaid_sum}, последний заказ {formatted_date}")
            
            # Обновляем статистику (смещено влево из-за удаления колонки Last Name)
            # F-I: Orders Count, Cancellations, Total Sum, Unpaid Sum
            users_sheet.update(f'F{user_row}:I{user_row}', 
                             [[str(active_orders), 
                               str(cancelled_orders), 
                               str(int(total_sum)),
                               str(int(unpaid_sum))]],  # Добавляем неоплаченную сумму
                             value_input_option='USER_ENTERED')
            logging.info(f"Ячейки F{user_row}:I{user_row} обновлены. Записаны значения: [{active_orders}, {cancelled_orders}, {int(total_sum)}, {int(unpaid_sum)}]")
            
            # Отдельно обновляем дату последнего заказа (теперь в столбце K)
            if formatted_date:
                users_sheet.update_cell(user_row, 11, formatted_date)
                logging.info(f"Ячейка K{user_row} (дата последнего заказа) обновлена на {formatted_date}")
        else:
            logging.error(f"Пользователь с ID '{user_id}' не найден в таблице Users")
            # Если пользователь не найден, пробуем создать запись о нем
            logging.info(f"Попытка создать новую запись для пользователя {user_id}")
            result = await update_user_info_by_id(user_id)
            if result:
                logging.info(f"Создана новая запись о пользователе {user_id}")
            else:
                logging.error(f"Не удалось создать запись о пользователе {user_id}")
                return False
        
        logging.info(f"Обновлена статистика пользователей в таблице Users")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обновлении статистики пользователя {user_id}: {e}")
        return False

async def update_user_info_by_id(user_id: str):
    """Создание базовой записи о пользователе по ID."""
    try:
        # Получаем информацию о пользователе из заказов
        all_orders = orders_sheet.get_all_values()
        user_orders = [order for order in all_orders[1:] if order[3] == user_id]
        
        # Получаем имя и номер комнаты из таблицы Auth
        auth_name = '-'
        room_number = ''
        try:
            auth_data = auth_sheet.get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                    auth_name = row[0] or '-'  # Берем имя из первого столбца
                    if len(row) >= 3 and row[2]:  # Проверяем наличие номера комнаты
                        room_number = row[2]  # Берем номер комнаты из третьего столбца
                    break
        except Exception as e:
            logging.error(f"Ошибка при получении данных из таблицы Auth: {e}")
        
        if user_orders:
            latest_order = user_orders[-1]
            username = latest_order[4]  # Username в пятом столбце
            profile_link = f"t.me/{username}" if username and username != '-' else '-'
            
            # Получаем все записи пользователей
            users_data = users_sheet.get_all_values()
            next_row = len(users_data) + 1
            
            # Добавляем базовую запись с новой структурой (без Last Name)
            new_user_row = [
                user_id,
                profile_link,
                auth_name,    # First Name из таблицы Auth
                '',           # Phone Number
                room_number,  # Room Number из таблицы Auth
                '0',          # Orders Count
                '0',          # Cancellations
                '0',          # Total Sum
                '0',          # Unpaid Sum
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Start Time
                ''            # Last Order Date
            ]
            # Используем явное указание диапазона вместо append_row
            users_sheet.update(f'A{next_row}:K{next_row}', [new_user_row], value_input_option='USER_ENTERED')
            logging.info(f"Новая базовая запись о пользователе {user_id} добавлена в строку {next_row}")
            if room_number:
                logging.info(f"Номер комнаты {room_number} сохранен для пользователя {user_id}")
            
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
                # Обновляем номер телефона (столбец D) - индекс смещен влево из-за удаления Last Name
                users_sheet.update(f'D{idx + 1}', [[phone]], value_input_option='USER_ENTERED')
                logging.info(f"Сохранен номер телефона для пользователя {user_id} в таблице Auth")
                return True
        return False
    except Exception as e:
        logging.error(f"Ошибка при сохранении номера телефона: {e}")
        return False

async def create_user_record(user_id: int, username: str, first_name: str, last_name: str) -> bool:
    try:
        # Получаем имя из таблицы Auth
        auth_name = '-'
        try:
            auth_data = auth_sheet.get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if len(row) >= 4 and row[3] == str(user_id):  # Если находим совпадение по user_id (четвертый столбец)
                    auth_name = row[0] or '-'  # Берем имя из первого столбца
                    break
        except Exception as e:
            logging.error(f"Ошибка при получении данных из таблицы Auth: {e}")
            
        # Используем имя из Auth или из параметров
        name_to_use = auth_name if auth_name != '-' else first_name
        profile_link = f"t.me/{username}" if username and username != '-' else '-'
        
        # Получаем все записи пользователей
        users_data = users_sheet.get_all_values()
        next_row = len(users_data) + 1
        
        # Добавляем запись с новой структурой
        new_user_row = [
            str(user_id),
            profile_link,
            name_to_use,    # First Name из Auth или параметров
            '',             # Phone Number
            '',             # Room Number
            '0',            # Orders Count
            '0',            # Cancellations
            '0',            # Total Sum
            '0',            # Unpaid Sum
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Start Time
            ''              # Last Order Date
        ]
        # Используем явное указание диапазона вместо append_row
        users_sheet.update(f'A{next_row}:K{next_row}', [new_user_row], value_input_option='USER_ENTERED')
        logging.info(f"Создана новая запись о пользователе {user_id} в таблице Users")
        return True
    except Exception as e:
        logging.error(f"Ошибка при создании записи о пользователе: {e}")
        return False

async def get_user_data(user_id: str) -> dict:
    """Получение данных пользователя (имя и номер комнаты) по его ID.
    
    Args:
        user_id: ID пользователя
        
    Returns:
        dict: Словарь с данными пользователя (name, room)
    """
    try:
        # Сначала ищем в таблице пользователей
        users_data = users_sheet.get_all_values()
        user_info = {'name': '-', 'room': ''}
        
        # Поиск в таблице пользователей
        for row in users_data[1:]:  # Пропускаем заголовок
            if row[0] == user_id:
                user_info['name'] = row[2]  # First Name
                user_info['room'] = row[4]  # Room Number
                break
        
        # Если в таблице пользователей нет имени или комнаты, проверяем Auth таблицу
        if user_info['name'] == '-' or not user_info['room']:
            try:
                auth_data = auth_sheet.get_all_values()
                for row in auth_data[1:]:  # Пропускаем заголовок
                    if len(row) >= 4 and row[3] == user_id:  # Если находим совпадение по user_id (четвертый столбец)
                        if user_info['name'] == '-':
                            user_info['name'] = row[0] or '-'  # Берем имя из первого столбца
                        if not user_info['room'] and len(row) >= 3 and row[2]:
                            user_info['room'] = row[2]  # Берем номер комнаты из третьего столбца
                        break
            except Exception as e:
                logging.error(f"Ошибка при получении данных из таблицы Auth: {e}")
        
        return user_info
    except Exception as e:
        logging.error(f"Ошибка при получении данных пользователя: {e}")
        return {'name': '-', 'room': ''} 