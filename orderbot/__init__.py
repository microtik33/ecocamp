"""
OrderBot - Telegram бот для заказа еды
"""
# Импортируем config первым для инициализации логирования
from . import config

# Импортируем остальные модули после инициализации логирования
from .services.sheets import update_orders_status
from .services.records import process_daily_orders 