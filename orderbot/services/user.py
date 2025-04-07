import gspread
from .. import config
from .sheets import client, orders_sheet, users_sheet
from .auth import auth_sheet
from datetime import datetime

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
                'Start Time',
                'Orders Count',
                'Cancellations',
                'Total Sum',
                'Last Order Date'
            ], value_input_option='USER_ENTERED')
            all_users = users_sheet.get_all_values()
        
        # Получаем номер телефона из таблицы Auth
        phone = ''
        try:
            # Получаем все значения из столбцов A (телефоны) и B (user_id)
            auth_data = auth_sheet.get_all_values()
            for row in auth_data[1:]:  # Пропускаем заголовок
                if row[1] == user_id:  # Если находим совпадение по user_id
                    phone = row[0]  # Берем номер телефона из первого столбца
                    break
        except Exception as e:
            print(f"Ошибка при получении номера телефона из таблицы Auth: {e}")
        
        user_found = False
        
        # Ищем пользователя и обновляем информацию
        for idx, row in enumerate(all_users[1:], start=2):  # Пропускаем заголовок
            if row[0] == user_id:
                # Обновляем основную информацию о пользователе массово
                users_sheet.update(f'A{idx}:F{idx}', 
                                 [[user_id, profile_link, first_name, last_name, phone, row[5] or start_time]],
                                 value_input_option='USER_ENTERED')
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
                phone,  # Phone Number из таблицы Auth
                start_time,  # Start Time
                '0',  # Orders Count
                '0',  # Cancellations
                '0',  # Total Sum
                ''    # Last Order Date
            ]
            users_sheet.append_row(new_user_row, value_input_option='USER_ENTERED')
            
        return True
    except Exception as e:
        print(f"Ошибка при обновлении информации о пользователе: {e}")
        return False

async def update_user_totals():
    """Обновление общей суммы заказов пользователей."""
    # Получаем все заказы
    all_orders = orders_sheet.get_all_values()
    
    # Создаем словарь для хранения сумм по пользователям
    user_totals = {}
    
    # Подсчитываем суммы активных заказов для каждого пользователя
    for order in all_orders[1:]:  # Пропускаем заголовок
        if order[2] == 'Активен':  # Проверяем статус заказа
            user_id = order[3]
            try:
                amount = float(order[5]) if order[5] else 0
                if user_id not in user_totals:
                    user_totals[user_id] = 0
                user_totals[user_id] += amount
            except (ValueError, IndexError) as e:
                print(f"Ошибка при обработке суммы заказа: {e}")
                continue
    
    # Получаем все записи о пользователях
    all_users = users_sheet.get_all_values()
    
    # Обновляем суммы в таблице пользователей
    for idx, row in enumerate(all_users[1:], start=2):  # Начинаем с 2, так как пропускаем заголовок
        user_id = row[0]
        total = user_totals.get(user_id, 0)
        users_sheet.update_cell(idx, 9, str(int(total)))  # Обновляем столбец I (9) - Total Sum

async def update_user_stats(user_id: str):
    """Обновление статистики пользователя."""
    try:
        # Получаем все заказы
        all_orders = orders_sheet.get_all_values()
        
        # Подсчитываем статистику пользователя
        active_orders = 0
        cancelled_orders = 0
        total_sum = 0
        last_order_date = None
        
        for order in all_orders[1:]:  # Пропускаем заголовок
            if order[3] == user_id:  # User ID в четвертом столбце
                order_date = order[1]  # Дата заказа во втором столбце
                if not last_order_date or order_date > last_order_date:
                    last_order_date = order_date
                
                if order[2] in ['Активен', 'Принят']:  # Учитываем активные и принятые заказы
                    active_orders += 1
                    total_sum += float(order[5]) if order[5] else 0  # Сумма в шестом столбце
                elif order[2] == 'Отменён':
                    cancelled_orders += 1
        
        # Получаем текущие данные пользователя
        users_data = users_sheet.get_all_values()
        user_row = None
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                user_row = idx + 1
                break
        
        if user_row:
            # Обновляем статистику (столбцы G-J: Orders Count, Cancellations, Total Sum, Last Order Date)
            users_sheet.update(f'G{user_row}:J{user_row}', 
                             [[str(active_orders), 
                               str(cancelled_orders), 
                               str(int(total_sum)),
                               last_order_date or '']],
                             value_input_option='USER_ENTERED')
        
        return True
    except Exception as e:
        print(f"Ошибка при обновлении статистики пользователя: {e}")
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
            
            # Добавляем базовую запись
            new_user_row = [
                user_id,
                profile_link,
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
            
            # Сразу обновляем статистику
            await update_user_stats(user_id)
            
        return True
    except Exception as e:
        print(f"Ошибка при создании записи о пользователе: {e}")
        return False

async def save_user_phone(user_id: str, phone: str):
    """Сохранение номера телефона пользователя."""
    try:
        users_data = users_sheet.get_all_values()
        for idx, row in enumerate(users_data):
            if row[0] == user_id:
                # Обновляем номер телефона (столбец E)
                users_sheet.update(f'E{idx + 1}', [[phone]], value_input_option='USER_ENTERED')
                return True
        return False
    except Exception as e:
        print(f"Ошибка при сохранении номера телефона: {e}")
        return False 