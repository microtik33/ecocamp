from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import logging
import tracemalloc
from ..utils.profiler import get_execution_stats, clear_stats, execution_stats
from ..services.sheets import is_user_cook
from ..utils.auth_decorator import require_auth

@require_auth
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
    
    # Параметры пагинации в user_data
    if 'stats_page' not in context.user_data:
        context.user_data['stats_page'] = 0
    
    # Если указан параметр page, обновляем номер страницы
    if context.args and len(context.args) > 0:
        try:
            page = int(context.args[0]) - 1  # Пользователи начинают счет с 1
            if page < 0:
                page = 0
            context.user_data['stats_page'] = page
        except:
            pass
    
    # Определяем количество функций на страницу
    items_per_page = 10
    total_funcs = len(sorted_stats)
    total_pages = (total_funcs + items_per_page - 1) // items_per_page
    
    # Текущая страница
    current_page = context.user_data['stats_page']
    if current_page >= total_pages:
        current_page = 0
        context.user_data['stats_page'] = 0
    
    # Получаем срез функций для текущей страницы
    start_idx = current_page * items_per_page
    end_idx = min(start_idx + items_per_page, total_funcs)
    page_stats = sorted_stats[start_idx:end_idx]
    
    # Формируем сообщение со статистикой
    message = f"📊 *Статистика времени выполнения* (стр. {current_page + 1}/{total_pages}):\n\n"
    
    for func_name, func_stats in page_stats:
        # Сокращаем имя функции для лучшей читаемости
        short_name = func_name.split('.')[-2:]
        short_name = '.'.join(short_name)
        
        message += f"*{short_name}*:\n"
        message += f"├ Мин: {func_stats['min']:.3f} сек\n"
        message += f"├ Макс: {func_stats['max']:.3f} сек\n"
        message += f"├ Средн: {func_stats['avg']:.3f} сек\n"
        message += f"└ Вызовов: {func_stats['count']}\n\n"
    
    # Добавляем навигацию
    message += f"_Показаны {start_idx + 1}-{end_idx} из {total_funcs} функций_\n\n"
    
    if total_pages > 1:
        message += "Используйте `/stats номер_страницы` для навигации между страницами"
    
    await update.message.reply_text(message, parse_mode="Markdown")

@require_auth
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

@require_auth
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

@require_auth
async def function_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для получения детальной статистики по конкретной функции.
    
    Использование: /funcstats имя_функции
    Например: /funcstats _update_menu_cache
    
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
    
    if not context.args or len(context.args) == 0:
        # Показываем список доступных функций
        stats = get_execution_stats()
        if not stats:
            await update.message.reply_text("Статистика еще не собрана. Попробуйте позже.")
            return
        
        # Получаем имена функций
        function_names = []
        for func_name in stats.keys():
            # Берем только имя функции без модуля
            short_name = func_name.split('.')[-1]
            function_names.append(short_name)
        
        # Сортируем имена по алфавиту
        function_names.sort()
        
        # Формируем сообщение со списком функций
        message = "*Доступные функции для анализа:*\n\n"
        message += '\n'.join([f"`{name}`" for name in function_names])
        message += "\n\nИспользуйте `/funcstats имя_функции` для получения подробной статистики."
        
        await update.message.reply_text(message, parse_mode="Markdown")
        return
    
    # Получаем имя функции из аргументов
    func_name = context.args[0]
    
    # Ищем функцию в статистике
    found_full_name = None
    for full_name in execution_stats.keys():
        if full_name.endswith('.' + func_name):
            found_full_name = full_name
            break
    
    if not found_full_name:
        await update.message.reply_text(f"Функция '{func_name}' не найдена в статистике.")
        return
    
    # Получаем все времена выполнения функции
    times = execution_stats[found_full_name]
    
    if not times:
        await update.message.reply_text(f"Нет данных о времени выполнения функции '{func_name}'.")
        return
    
    # Вычисляем статистику
    min_time = min(times)
    max_time = max(times)
    avg_time = sum(times) / len(times)
    
    # Формируем сообщение со статистикой
    message = f"📊 *Детальная статистика для функции* `{func_name}`:\n\n"
    message += f"*Модуль:* `{'.'.join(found_full_name.split('.')[:-1])}`\n"
    message += f"*Количество вызовов:* {len(times)}\n\n"
    message += f"*Минимальное время:* {min_time:.3f} сек\n"
    message += f"*Максимальное время:* {max_time:.3f} сек\n"
    message += f"*Среднее время:* {avg_time:.3f} сек\n"
    message += f"*Общее время:* {sum(times):.3f} сек\n\n"
    
    # Добавляем гистограмму времени выполнения, если вызовов больше 5
    if len(times) > 5:
        # Разбиваем на 5 диапазонов от min до max
        range_size = (max_time - min_time) / 5
        ranges = []
        
        for i in range(5):
            start = min_time + i * range_size
            end = min_time + (i + 1) * range_size
            if i == 4:  # Последний диапазон
                end = max_time + 0.001  # Добавляем небольшое значение, чтобы включить max
            
            count = sum(1 for t in times if start <= t < end)
            percentage = (count / len(times)) * 100
            bar = "█" * int(percentage / 5)  # Каждые 5% - один символ
            
            ranges.append((start, end, count, percentage, bar))
        
        message += "*Распределение времени выполнения:*\n"
        
        for start, end, count, percentage, bar in ranges:
            message += f"{start:.2f}s - {end:.2f}s: {bar} {count} ({percentage:.1f}%)\n"
    
    await update.message.reply_text(message, parse_mode="Markdown") 