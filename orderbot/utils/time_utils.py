from datetime import datetime, time

def is_order_time():
    """Проверяет, можно ли сейчас сделать заказ (с 10:00 до 00:00)."""
    current_time = datetime.now().time()
    start_time = time(10, 0)  # 10:00
    end_time = time(0, 0)    # 00:00
    
    # Если текущее время между 10:00 и 00:00
    if start_time <= current_time or current_time < end_time:
        return True
    return False

def is_menu_available_time():
    """Проверяет, доступно ли сейчас меню на завтра (с 10:00 до 00:00).
    
    Меню на следующий день становится доступным после 10:00 и 
    остается доступным до полуночи.
    """
    return is_order_time()  # Используем ту же логику, что и для времени заказа 