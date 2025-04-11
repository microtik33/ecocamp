import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .. import translations
from ..services.user import update_user_info
from ..utils.time_utils import is_order_time
from .order import MENU
from ..services.sheets import get_dishes_for_meal

async def start(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом."""
    context.user_data.clear()
    
    # Обновляем информацию о пользователе
    user = update.effective_user
    await update_user_info(user)
    
    # Проверяем время для заказа
    can_order = is_order_time()
    make_order_button = InlineKeyboardButton(
        translations.get_button('make_order'), 
        callback_data='new_order'
    ) if can_order else InlineKeyboardButton(
        translations.get_button('make_order') + ' ⛔', 
        callback_data='order_time_error'
    )
    
    # Отправляем приветственное сообщение
    keyboard = [
        [make_order_button],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('tomorrow_menu'), callback_data='tomorrow_menu')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(translations.get_message('welcome'), reply_markup=reply_markup)
    return MENU

async def show_tomorrow_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показывает меню на завтра."""
    query = update.callback_query
    await query.answer()
    
    # Получаем блюда для каждого приема пищи
    breakfast_dishes = get_dishes_for_meal('breakfast')
    lunch_dishes = get_dishes_for_meal('lunch')
    dinner_dishes = get_dishes_for_meal('dinner')
    
    # Формируем сообщение с меню
    message = "🍽 *Меню на завтра*\n\n"
    
    # Добавляем завтрак
    message += "🍳 *Завтрак:*\n"
    if breakfast_dishes:
        for dish, price in breakfast_dishes:
            message += f"• {dish} - {price} р.\n"
    else:
        message += "Меню пока недоступно\n"
    
    # Добавляем обед
    message += "\n🍲 *Обед:*\n"
    if lunch_dishes:
        for dish, price in lunch_dishes:
            message += f"• {dish} - {price} р.\n"
    else:
        message += "Меню пока недоступно\n"
    
    # Добавляем ужин
    message += "\n🍽 *Ужин:*\n"
    if dinner_dishes:
        for dish, price in dinner_dishes:
            message += f"• {dish} - {price} р.\n"
    else:
        message += "Меню пока недоступно\n"
    
    # Добавляем кнопки для возврата в меню
    keyboard = [
        [InlineKeyboardButton(translations.get_button('make_order'), callback_data='new_order')],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    return MENU 