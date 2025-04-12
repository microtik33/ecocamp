from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from ..services.kitchen import get_orders_summary
from ..services.sheets import is_user_cook
from .. import translations
from ..utils.auth_decorator import require_auth

@require_auth
async def kitchen_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает сводку по заказам для повара."""
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    # Получаем сводку по заказам
    summary = get_orders_summary()
    
    # Отправляем общую информацию
    general_message = f"📊 Заказы на *{summary['date']}*:\n\n"
    general_message += f"📝 Всего заказов: {summary['total_orders']}\n"
    await update.message.reply_text(general_message, parse_mode=ParseMode.MARKDOWN)
    
    # Отправляем информацию о завтраке
    breakfast_message = f"🍳 *Завтрак* (всего заказов: {summary['breakfast']['count']}):\n\n"
    if summary['breakfast']['dishes']:
        breakfast_message += "Блюда:\n"
        for dish, count in sorted(summary['breakfast']['dishes'].items()):
            breakfast_message += f"- {dish}: {count} шт.\n"
        breakfast_message += "\nЗаказы:\n\n"
        for order in summary['breakfast']['orders']:
            breakfast_message += f"{order}\n"
    else:
        breakfast_message += "Нет заказов\n"
    await update.message.reply_text(breakfast_message, parse_mode=ParseMode.MARKDOWN)
    
    # Отправляем информацию об обеде
    lunch_message = f"🍲 *Обед* (всего заказов: {summary['lunch']['count']}):\n\n"
    if summary['lunch']['dishes']:
        lunch_message += "Блюда:\n"
        for dish, count in sorted(summary['lunch']['dishes'].items()):
            lunch_message += f"- {dish}: {count} шт.\n"
        lunch_message += "\nЗаказы:\n\n"
        for order in summary['lunch']['orders']:
            lunch_message += f"{order}\n"
    else:
        lunch_message += "Нет заказов\n"
    await update.message.reply_text(lunch_message, parse_mode=ParseMode.MARKDOWN)
    
    # Отправляем информацию об ужине
    dinner_message = f"🍽 *Ужин* (всего заказов: {summary['dinner']['count']}):\n\n"
    if summary['dinner']['dishes']:
        dinner_message += "Блюда:\n"
        for dish, count in sorted(summary['dinner']['dishes'].items()):
            dinner_message += f"- {dish}: {count} шт.\n"
        dinner_message += "\nЗаказы:\n\n"
        for order in summary['dinner']['orders']:
            dinner_message += f"{order}\n"
    else:
        dinner_message += "Нет заказов\n"
    await update.message.reply_text(dinner_message, parse_mode=ParseMode.MARKDOWN) 