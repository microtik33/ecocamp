import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
import logging
from .. import translations
from ..services import sheets
from ..utils.time_utils import is_order_time
from ..utils.auth_decorator import require_auth
from .states import MENU, QUESTION

# Настройка логгера
logger = logging.getLogger(__name__)

@require_auth
async def handle_question(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработка вопросов."""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(translations.get_button('back'), callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=translations.get_message('ask_question'),
        reply_markup=reply_markup
    )
    return QUESTION

async def save_question(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Сохранение вопроса."""
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or '-'
    question_text = update.message.text
    
    # Сохраняем вопрос в таблицу
    await sheets.save_question(user_id, question_text)
    
    # Получаем информацию о пользователе для отправки администраторам
    users_data = sheets.get_users_sheet().get_all_values()
    phone = '-'
    for row in users_data[1:]:  # Пропускаем заголовок
        if row[0] == user_id:
            phone = row[4]  # Phone Number
            break
    
    # Форматируем сообщение для администраторов
    now = datetime.now()
    formatted_date = now.strftime("%d.%m.%Y %H:%M")
    admin_message = f"Вопрос от @{username} ({phone})\n{formatted_date}\n{question_text}"
    
    # Отправляем вопрос администраторам
    admin_ids = sheets.get_admins_ids()
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_message)
            logging.info(f"Вопрос отправлен администратору {admin_id}")
        except Exception as e:
            logging.error(f"Ошибка при отправке вопроса администратору {admin_id}: {e}")
    
    # Возвращаем пользователя в главное меню
    # Проверяем время для заказа
    can_order = is_order_time()
    make_order_button = InlineKeyboardButton(
        translations.get_button('make_order'), 
        callback_data='new_order'
    ) if can_order else InlineKeyboardButton(
        translations.get_button('make_order') + ' ⛔', 
        callback_data='order_time_error'
    )
    
    # Проверяем, доступно ли меню
    menu_button = InlineKeyboardButton(
        translations.get_button('tomorrow_menu'), 
        callback_data='tomorrow_menu'
    )
    
    # Отправляем клавиатуру с кнопками
    keyboard = [
        [make_order_button],
        [menu_button],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(translations.get_message('question_thanks'), reply_markup=reply_markup)
    return MENU 