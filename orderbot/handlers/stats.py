from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import logging
import tracemalloc
from ..utils.profiler import get_execution_stats, clear_stats
from ..services.sheets import is_user_cook

async def performance_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для получения статистики производительности бота.
    
    Только для поваров и админов.
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем права доступа (только для поваров)
    if not is_user_cook(user_id):
        await update.message.reply_text("У вас нет прав на просмотр статистики производительности.")
        return
    
    # Получаем статистику выполнения функций
    stats = get_execution_stats()
    
    if not stats:
        await update.message.reply_text("Статистика еще не собрана. Попробуйте позже.")
        return
    
    # Сортируем функции по среднему времени выполнения (от наибольшего к наименьшему)
    sorted_stats = sorted(
        stats.items(), 
        key=lambda x: x[1]["avg"], 
        reverse=True
    )
    
    # Формируем сообщение со статистикой
    message = "📊 *Статистика времени выполнения*:\n\n"
    
    for func_name, func_stats in sorted_stats[:10]:  # Выводим только 10 самых долгих функций
        # Сокращаем имя функции для лучшей читаемости
        short_name = func_name.split('.')[-2:]
        short_name = '.'.join(short_name)
        
        message += f"*{short_name}*:\n"
        message += f"├ Мин: {func_stats['min']:.3f} сек\n"
        message += f"├ Макс: {func_stats['max']:.3f} сек\n"
        message += f"├ Средн: {func_stats['avg']:.3f} сек\n"
        message += f"└ Вызовов: {func_stats['count']}\n\n"
    
    total_funcs = len(stats)
    if total_funcs > 10:
        message += f"_Показаны 10 из {total_funcs} функций_"
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def clear_performance_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Очищает собранную статистику производительности.
    
    Только для поваров и админов.
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем права доступа (только для поваров)
    if not is_user_cook(user_id):
        await update.message.reply_text("У вас нет прав на очистку статистики производительности.")
        return
    
    # Очищаем статистику
    clear_stats()
    
    await update.message.reply_text("Статистика производительности очищена.")

async def memory_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для получения статистики использования памяти ботом.
    
    Только для поваров и админов.
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем права доступа (только для поваров)
    if not is_user_cook(user_id):
        await update.message.reply_text("У вас нет прав на просмотр статистики памяти.")
        return
    
    # Получаем текущий снимок использования памяти
    snapshot = tracemalloc.take_snapshot()
    
    # Группируем по файлам и строкам
    top_stats = snapshot.statistics('lineno')
    
    # Формируем сообщение со статистикой
    message = "📊 *Статистика использования памяти*:\n\n"
    
    for stat in top_stats[:10]:  # Только 10 самых крупных объектов
        # Сокращаем путь к файлу для лучшей читаемости
        filename = stat.traceback[0].filename.split('/')[-2:]
        filename = '/'.join(filename)
        
        line = stat.traceback[0].lineno
        size_kb = stat.size / 1024  # Размер в килобайтах
        
        message += f"*{filename}:{line}*:\n"
        message += f"└ Размер: {size_kb:.2f} КБ\n\n"
    
    total = sum(stat.size for stat in top_stats)
    total_kb = total / 1024
    message += f"*Всего используется*: {total_kb:.2f} КБ\n"
    
    if len(top_stats) > 10:
        message += f"_Показаны 10 из {len(top_stats)} записей_"
    
    await update.message.reply_text(message, parse_mode="Markdown") 