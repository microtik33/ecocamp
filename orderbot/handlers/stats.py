from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import logging
from ..utils.profiler import get_execution_stats, clear_stats
from ..services.sheets import is_user_admin
from ..utils.auth_decorator import require_auth

@require_auth
async def performance_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для получения статистики производительности бота.
    
    Только для администраторов.
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем права доступа (только для администраторов)
    if not is_user_admin(user_id):
        await update.message.reply_text("У вас нет доступа к этой команде.")
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
    
    Только для администраторов.
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем права доступа (только для администраторов)
    if not is_user_admin(user_id):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    # Очищаем статистику
    clear_stats()
    
    await update.message.reply_text("Статистика производительности очищена.") 