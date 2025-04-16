import asyncio
from datetime import datetime, time, timedelta
import logging
import pytz

# Импортируем функции так, чтобы их можно было мокать
from .services.sheets import (
    update_orders_status, 
    force_update_menu_cache,
    force_update_composition_cache
)
from .services.records import process_daily_orders

# Глобальная переменная для хранения задачи
_status_update_task = None

# Устанавливаем часовой пояс для Москвы
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

async def check_orders_status():
    """Проверяет и обновляет статусы заказов при запуске бота."""
    try:
        await update_orders_status()
        logging.info("Статусы заказов проверены при запуске бота")
    except Exception as e:
        logging.error(f"Ошибка при проверке статусов заказов при запуске: {e}")

async def schedule_status_update():
    """Планирует обновление статусов заказов каждый день в полночь по московскому времени."""
    try:
        # Сначала проверяем статусы при запуске
        await check_orders_status()
        
        while True:
            # Получаем текущее время в московском часовом поясе
            now = datetime.now(MOSCOW_TZ)
            
            # Вычисляем время до следующей полночи по московскому времени
            midnight = datetime.combine(now.date() + timedelta(days=1), time(), tzinfo=MOSCOW_TZ)
            wait_seconds = (midnight - now).total_seconds()
            
            # Ждем до полуночи
            await asyncio.sleep(wait_seconds)
            
            # Обновляем статусы заказов
            await update_orders_status()
            
            # Ждем 1 секунду, чтобы избежать повторного выполнения в ту же секунду
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logging.info("Задача обновления статусов остановлена")
    except Exception as e:
        logging.error(f"Ошибка в задаче обновления статусов: {e}")

def start_status_update_task():
    """Запускает задачу обновления статусов."""
    global _status_update_task
    if _status_update_task is None:
        loop = asyncio.get_event_loop()
        _status_update_task = loop.create_task(schedule_status_update())
        logging.info("Задача обновления статусов запущена")

def stop_status_update_task():
    """Останавливает задачу обновления статусов."""
    global _status_update_task
    if _status_update_task is not None:
        _status_update_task.cancel()
        _status_update_task = None
        logging.info("Задача обновления статусов остановлена")

async def process_daily_tasks():
    """Обрабатывает ежедневные задачи.
    
    Выполняет обработку заказов за день.
    """
    # Обновляем статусы заказов
    try:
        await update_orders_status()
        logging.info("Статусы заказов обновлены")
    except Exception as e:
        logging.error(f"Ошибка при обновлении статусов заказов: {e}")
    
    # Ждем 1 минуту после смены статусов
    await asyncio.sleep(60)
    logging.info("Прошла минута ожидания, начинаем обработку")
    
    # Запускаем обработку заказов за день
    try:
        await process_daily_orders()
        logging.info("Обработка заказов завершена успешно")
    except Exception as e:
        logging.error(f"Ошибка при обработке заказов: {e}")

async def schedule_daily_tasks():
    """Планировщик ежедневных задач."""
    logging.info("Запуск планировщика ежедневных задач")
    while True:
        # Получаем текущее время
        now = datetime.now()
        current_time = now.time()
        logging.info(f"Текущее время: {current_time.strftime('%H:%M:%S')}")
        
        # Если сейчас полночь (00:00) - обрабатываем заказы
        if current_time.hour == 0 and current_time.minute == 0:
            logging.info("Наступила полночь, начинаем обработку заказов")
            # Обновляем статусы заказов и обрабатываем их
            try:
                await update_orders_status()
                logging.info("Статусы заказов обновлены")
                
                # Ждем 1 минуту после смены статусов
                await asyncio.sleep(60)
                logging.info("Прошла минута ожидания, начинаем обработку")
                
                # Запускаем обработку заказов за день
                await process_daily_orders()
                logging.info("Обработка заказов завершена успешно")
            except Exception as e:
                logging.error(f"Ошибка при обработке заказов: {e}")
        
        # Если сейчас 9:59 - обновляем кэш меню
        elif current_time.hour == 9 and current_time.minute == 59:
            logging.info("Наступило 9:59, начинаем обновление меню")
            # Принудительно обновляем кэш меню и составов
            try:
                await force_update_menu_cache()
                logging.info("Кэш меню принудительно обновлен")
                
                await force_update_composition_cache()
                logging.info("Кэш составов блюд принудительно обновлен")
            except Exception as e:
                logging.error(f"Ошибка при обновлении кэша: {e}")
        else:
            logging.info(f"Не время для выполнения задач (сейчас {current_time.hour:02d}:{current_time.minute:02d}), пропускаем обработку")
        
        # Проверяем каждую минуту
        await asyncio.sleep(60) 