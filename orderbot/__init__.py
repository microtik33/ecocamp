"""
OrderBot - Telegram бот для заказа еды
"""
from . import config  # Импортируем config первым для инициализации логирования
from .services.sheets import update_orders_status
from .services.records import process_daily_orders 