from datetime import datetime, date, timedelta
from .sheets import orders_sheet, rec_sheet, auth_sheet
from collections import defaultdict
import logging

def normalize_date(date_str: str) -> str:
    """
    Нормализует дату в формат YYYY-MM-DD.
    
    Args:
        date_str: Дата в одном из форматов: YYYY-MM-DD, DD.MM.YY, DD.MM.YYYY, D.M.YYYY
        
    Returns:
        str: Дата в формате YYYY-MM-DD
    """
    try:
        # Пробуем разные форматы даты
        for fmt in ["%Y-%m-%d", "%d.%m.%y", "%d.%m.%Y", "%d.%m.%Y"]:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str  # Если ни один формат не подошел, возвращаем исходную строку
    except Exception:
        return date_str

async def process_daily_orders():
    """Обработка заказов за текущий день и сохранение их в таблицу Rec."""
    try:
        logging.info("Начало обработки заказов за день")
        
        # Получаем текущую дату
        current_date = date.today().strftime("%Y-%m-%d")  # Оставляем для сравнения
        current_date_formatted = date.today().strftime("%d.%m.%y")  # Для записи в таблицу
        logging.info(f"Обработка заказов за дату: {current_date_formatted}")
        
        # Получаем все заказы
        all_orders = orders_sheet.get_all_values()
        logging.info(f"Всего заказов в таблице: {len(all_orders) - 1}")  # -1 для учета заголовка
        
        # Фильтруем заказы за текущий день
        daily_orders = [
            order for order in all_orders[1:]  # Пропускаем заголовок
            if normalize_date(order[11]) == current_date  # Проверяем дату выдачи
        ]
        logging.info(f"Заказов за текущий день: {len(daily_orders)}")
        
        # Получаем все записи из таблицы Rec
        rec_data = rec_sheet.get_all_values()
        logging.info(f"Текущих записей в таблице Rec: {len(rec_data) - 1}")
        
        # Если лист пустой, добавляем заголовки
        if not rec_data:
            logging.info("Таблица Rec пуста, добавляем заголовки")
            rec_sheet.append_row([
                'Дата выдачи',
                'Количество заказов',
                'Количество отмен',
                'Общая сумма',
                'Завтрак',
                'Обед',
                'Ужин'
            ], value_input_option='USER_ENTERED')
            rec_data = rec_sheet.get_all_values()
        
        # Подсчитываем статистику
        # Учитываем все заказы, которые были приняты в течение дня
        accepted_orders = [order for order in daily_orders if order[2] in ["Принят", "Активен"]]
        cancelled_orders = [order for order in daily_orders if order[2] == "Отменён"]
        
        logging.info(f"Принятых заказов: {len(accepted_orders)}")
        logging.info(f"Отмененных заказов: {len(cancelled_orders)}")
        
        total_orders = len(accepted_orders)
        total_cancelled = len(cancelled_orders)
        total_amount = sum(float(order[5]) for order in accepted_orders if order[5])
        logging.info(f"Общая сумма заказов: {total_amount}")
        
        # Собираем блюда по типам приема пищи
        breakfast_dishes = defaultdict(int)
        lunch_dishes = defaultdict(int)
        dinner_dishes = defaultdict(int)
        
        for order in accepted_orders:
            meal_type = order[8]  # Тип еды, берем оригинальное значение (без приведения к нижнему регистру)
            dishes_str = order[9]  # Строка с блюдами
            
            # Парсим строку с блюдами
            for dish_info in dishes_str.split(', '):
                if ' x' in dish_info:
                    dish, quantity = dish_info.split(' x')
                    quantity = int(quantity)
                else:
                    dish = dish_info
                    quantity = 1
                
                # Добавляем блюдо в соответствующий словарь
                if meal_type == 'Завтрак':
                    breakfast_dishes[dish] += quantity
                elif meal_type == 'Обед':
                    lunch_dishes[dish] += quantity
                elif meal_type == 'Ужин':
                    dinner_dishes[dish] += quantity
        
        logging.info(f"Блюд на завтрак: {len(breakfast_dishes)}")
        logging.info(f"Блюд на обед: {len(lunch_dishes)}")
        logging.info(f"Блюд на ужин: {len(dinner_dishes)}")
        
        # Форматируем строки с блюдами
        breakfast_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in breakfast_dishes.items())
        lunch_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in lunch_dishes.items())
        dinner_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in dinner_dishes.items())
        
        # Формируем строку данных
        row_data = [
            current_date_formatted,  # Используем отформатированную дату
            str(total_orders),
            str(total_cancelled),
            str(int(total_amount)),
            breakfast_str or '—',
            lunch_str or '—',
            dinner_str or '—'
        ]
        
        # Проверяем, существует ли уже запись за этот день
        existing_row = None
        for idx, row in enumerate(rec_data[1:], start=2):  # Пропускаем заголовок
            if normalize_date(row[0]) == current_date:  # Нормализуем дату для сравнения
                existing_row = idx
                break
        
        if existing_row:
            logging.info(f"Обновляем существующую запись в строке {existing_row}")
            # Обновляем существующую запись
            rec_sheet.update(f'A{existing_row}:G{existing_row}', [row_data], value_input_option='USER_ENTERED')
        else:
            logging.info("Добавляем новую запись")
            # Добавляем новую запись
            rec_sheet.append_row(row_data, value_input_option='USER_ENTERED')
        
        logging.info("Обработка заказов успешно завершена")
        return True
    except Exception as e:
        logging.error(f"Ошибка при обработке заказов за день: {e}")
        return False 

async def recount_last_three_days():
    """Пересчитывает данные в таблице Rec за последние 3 дня.
    
    Returns:
        bool: True в случае успешного пересчета, False в противном случае
    """
    try:
        logging.info("Начало пересчета данных за последние 3 дня")
        
        # Получаем даты за последние 3 дня
        today = date.today()
        dates_to_process = []
        for i in range(3):
            target_date = today - timedelta(days=i)
            dates_to_process.append(target_date)
        
        logging.info(f"Пересчитываем данные за даты: {[d.strftime('%d.%m.%y') for d in dates_to_process]}")
        
        # Получаем все заказы
        all_orders = orders_sheet.get_all_values()
        logging.info(f"Всего заказов в таблице: {len(all_orders) - 1}")  # -1 для учета заголовка
        
        # Получаем все записи из таблицы Rec
        rec_data = rec_sheet.get_all_values()
        logging.info(f"Текущих записей в таблице Rec: {len(rec_data) - 1}")
        
        # Если лист пустой, добавляем заголовки
        if not rec_data:
            logging.info("Таблица Rec пуста, добавляем заголовки")
            rec_sheet.append_row([
                'Дата выдачи',
                'Количество заказов',
                'Количество отмен',
                'Общая сумма',
                'Завтрак',
                'Обед',
                'Ужин'
            ], value_input_option='USER_ENTERED')
            rec_data = rec_sheet.get_all_values()
        
        # Обрабатываем каждую дату
        for target_date in dates_to_process:
            current_date = target_date.strftime("%Y-%m-%d")  # Для сравнения
            current_date_formatted = target_date.strftime("%d.%m.%y")  # Для записи в таблицу
            
            logging.info(f"Обработка заказов за дату: {current_date_formatted}")
            
            # Фильтруем заказы за текущую дату
            daily_orders = [
                order for order in all_orders[1:]  # Пропускаем заголовок
                if normalize_date(order[11]) == current_date  # Проверяем дату выдачи
            ]
            logging.info(f"Заказов за {current_date_formatted}: {len(daily_orders)}")
            
            # Подсчитываем статистику
            # Учитываем все заказы, которые были приняты в течение дня
            accepted_orders = [order for order in daily_orders if order[2] in ["Принят", "Активен", "Ожидает оплаты", "Оплачен"]]
            cancelled_orders = [order for order in daily_orders if order[2] == "Отменён"]
            
            logging.info(f"Принятых заказов за {current_date_formatted}: {len(accepted_orders)}")
            logging.info(f"Отмененных заказов за {current_date_formatted}: {len(cancelled_orders)}")
            
            total_orders = len(accepted_orders)
            total_cancelled = len(cancelled_orders)
            total_amount = sum(float(order[5]) for order in accepted_orders if order[5])
            logging.info(f"Общая сумма заказов за {current_date_formatted}: {total_amount}")
            
            # Собираем блюда по типам приема пищи
            breakfast_dishes = defaultdict(int)
            lunch_dishes = defaultdict(int)
            dinner_dishes = defaultdict(int)
            
            for order in accepted_orders:
                meal_type = order[8]  # Тип еды
                dishes_str = order[9]  # Строка с блюдами
                
                # Парсим строку с блюдами
                for dish_info in dishes_str.split(', '):
                    if ' x' in dish_info:
                        dish, quantity = dish_info.split(' x')
                        quantity = int(quantity)
                    else:
                        dish = dish_info
                        quantity = 1
                    
                    # Добавляем блюдо в соответствующий словарь
                    if meal_type == 'Завтрак':
                        breakfast_dishes[dish] += quantity
                    elif meal_type == 'Обед':
                        lunch_dishes[dish] += quantity
                    elif meal_type == 'Ужин':
                        dinner_dishes[dish] += quantity
            
            # Форматируем строки с блюдами
            breakfast_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in breakfast_dishes.items())
            lunch_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in lunch_dishes.items())
            dinner_str = ', '.join(f"{dish} x{quantity}" for dish, quantity in dinner_dishes.items())
            
            # Формируем строку данных
            row_data = [
                current_date_formatted,  # Используем отформатированную дату
                str(total_orders),
                str(total_cancelled),
                str(int(total_amount)),
                breakfast_str or '—',
                lunch_str or '—',
                dinner_str or '—'
            ]
            
            # Проверяем, существует ли уже запись за этот день
            existing_row = None
            for idx, row in enumerate(rec_data[1:], start=2):  # Пропускаем заголовок
                if normalize_date(row[0]) == current_date:  # Нормализуем дату для сравнения
                    existing_row = idx
                    break
            
            if existing_row:
                logging.info(f"Обновляем существующую запись в строке {existing_row} для даты {current_date_formatted}")
                # Обновляем существующую запись
                rec_sheet.update(f'A{existing_row}:G{existing_row}', [row_data], value_input_option='USER_ENTERED')
            else:
                logging.info(f"Добавляем новую запись для даты {current_date_formatted}")
                # Добавляем новую запись
                rec_sheet.append_row(row_data, value_input_option='USER_ENTERED')
                # Обновляем rec_data для следующих итераций
                rec_data.append(row_data)
        
        logging.info("Пересчет данных за последние 3 дня успешно завершен")
        return True
    except Exception as e:
        logging.error(f"Ошибка при пересчете данных за последние 3 дня: {e}")
        return False 