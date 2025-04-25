from collections import defaultdict
from .sheets import orders_sheet
from datetime import datetime

def get_dishes_count():
    """
    Подсчитывает количество каждого блюда во всех принятых заказах на текущий день.
    Возвращает словарь, где ключ - название блюда, значение - количество.
    """
    # Получаем все заказы
    all_orders = orders_sheet.get_all_values()
    today = datetime.now().date()
    
    # Создаем словарь для подсчета блюд
    dishes_count = defaultdict(int)
    
    # Пропускаем заголовок и обрабатываем каждый заказ
    for order in all_orders[1:]:
        # Проверяем, что заказ принят, ожидает оплаты, оплачен и на сегодня
        if (order[2] == 'Принят' or order[2] == 'Ожидает оплаты' or order[2] == 'Оплачен') and order[11]:
            try:
                delivery_date = datetime.strptime(order[11], "%d.%m.%y").date()
                if delivery_date == today:
                    # Получаем список блюд из заказа
                    dishes = [dish.strip() for dish in order[9].split(',')]
                    # Увеличиваем счетчик для каждого блюда
                    for dish in dishes:
                        dishes_count[dish] += 1
            except ValueError:
                continue
    
    return dict(dishes_count)

def get_orders_summary():
    """
    Возвращает сводку по всем принятым заказам, заказам, ожидающим оплаты, и оплаченным заказам на текущий день, группируя блюда по приемам пищи.
    """
    # Получаем все заказы
    all_orders = orders_sheet.get_all_values()
    today = datetime.now().date()
    
    # Создаем словари для подсчета блюд по приемам пищи
    breakfast_dishes = defaultdict(int)
    lunch_dishes = defaultdict(int)
    dinner_dishes = defaultdict(int)
    
    # Создаем списки для хранения детальной информации о заказах
    breakfast_orders = []
    lunch_orders = []
    dinner_orders = []
    
    total_orders = 0
    
    # Пропускаем заголовок и обрабатываем каждый заказ
    for order in all_orders[1:]:
        # Проверяем, что заказ принят, ожидает оплаты, оплачен и на сегодня
        if (order[2] == 'Принят' or order[2] == 'Ожидает оплаты' or order[2] == 'Оплачен') and order[11]:
            try:
                delivery_date = datetime.strptime(order[11], "%d.%m.%y").date()
                if delivery_date == today:
                    total_orders += 1
                    
                    # Получаем тип приема пищи и список блюд
                    meal_type = order[8]  # Тип еды: Завтрак, Обед или Ужин
                    dishes = [dish.strip() for dish in order[9].split(',')]
                    wishes = order[10] if order[10] and order[10] != "—" else None
                    
                    # Добавляем отметку для заказов в зависимости от статуса
                    status_mark = ""
                    if order[2] == 'Ожидает оплаты':
                        status_mark = "💰 "
                    elif order[2] == 'Оплачен':
                        status_mark = "✅ "
                    
                    # Формируем описание заказа
                    order_description = f"{status_mark}Заказ *№{order[0]}*\n"
                    order_description += f"🏠 Комната: *{order[6]}*\n"
                    order_description += f"👤 Имя: *{order[7]}*\n"
                    for dish in dishes:
                        order_description += f"• {dish}\n"
                    if wishes:
                        order_description += f"Пожелания: *{wishes}*\n"
                    order_description += "─" * 30 # Разделитель между заказами
                    
                    # Добавляем заказ в соответствующий список
                    if meal_type == 'Завтрак':
                        breakfast_orders.append(order_description)
                        for dish in dishes:
                            # Разбираем строку с блюдом и количеством
                            if ' x' in dish:
                                dish_name, quantity = dish.split(' x')
                                breakfast_dishes[dish_name] += int(quantity)
                            else:
                                breakfast_dishes[dish] += 1
                    elif meal_type == 'Обед':
                        lunch_orders.append(order_description)
                        for dish in dishes:
                            if ' x' in dish:
                                dish_name, quantity = dish.split(' x')
                                lunch_dishes[dish_name] += int(quantity)
                            else:
                                lunch_dishes[dish] += 1
                    elif meal_type == 'Ужин':
                        dinner_orders.append(order_description)
                        for dish in dishes:
                            if ' x' in dish:
                                dish_name, quantity = dish.split(' x')
                                dinner_dishes[dish_name] += int(quantity)
                            else:
                                dinner_dishes[dish] += 1
            except ValueError:
                continue
    
    # Формируем итоговую сводку
    summary = {
        'total_orders': total_orders,
        'date': today.strftime("%d.%m.%Y"),  # Добавляем дату в формате DD.MM.YYYY
        'breakfast': {
            'count': len(breakfast_orders),
            'dishes': dict(breakfast_dishes),
            'orders': breakfast_orders
        },
        'lunch': {
            'count': len(lunch_orders),
            'dishes': dict(lunch_dishes),
            'orders': lunch_orders
        },
        'dinner': {
            'count': len(dinner_orders),
            'dishes': dict(dinner_dishes),
            'orders': dinner_orders
        }
    }
    
    return summary 