import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.constants import ParseMode
from datetime import datetime
import logging
import os
from .. import translations
from ..services import sheets
from ..utils.time_utils import is_order_time
from ..utils.auth_decorator import require_auth
from .states import MENU, QUESTION

# Настройка логгера
logger = logging.getLogger(__name__)

def escape_markdown_v2(text):
    """
    Экранирует специальные символы Markdown V2 в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Текст с экранированными специальными символами
    """
    if not text:
        return ""
    
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', 
                    '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    
    return text

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
            # Добавляем "+" к номеру телефона, если его еще нет
            if phone and phone != '-' and not phone.startswith('+'):
                phone = f"+{phone}"
            break
    
    # Форматируем сообщение для администраторов
    now = datetime.now()
    formatted_date = now.strftime("%d.%m.%Y %H:%M")
    
    # Экранируем специальные символы для MarkdownV2
    escaped_username = escape_markdown_v2(username)
    escaped_phone = escape_markdown_v2(phone)
    escaped_date = escape_markdown_v2(formatted_date)
    escaped_question = escape_markdown_v2(question_text)
    
    admin_message = f"❓ *Вопрос от* @{escaped_username} \\({escaped_phone}\\)\n_{escaped_date}_\n\n{escaped_question}"
    
    # Путь к изображению (в текущей директории handlers)
    image_path = os.path.join(os.path.dirname(__file__), 'question.png')
    
    # Отправляем вопрос администраторам
    admin_ids = sheets.get_admins_ids()
    for admin_id in admin_ids:
        try:
            # Проверяем существование файла изображения
            if os.path.exists(image_path):
                # Отправляем изображение с подписью
                with open(image_path, 'rb') as photo:
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=photo,
                        caption=admin_message,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                # Если изображение не найдено, отправляем только текст
                await context.bot.send_message(
                    chat_id=admin_id, 
                    text=admin_message,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            logging.info(f"Вопрос отправлен администратору {admin_id}")
        except Exception as e:
            logging.error(f"Ошибка при отправке вопроса администратору {admin_id}: {e}")
            # Пробуем отправить хотя бы текст, если возникла ошибка с изображением
            try:
                await context.bot.send_message(
                    chat_id=admin_id, 
                    text=admin_message,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                logging.info(f"Отправлен только текст вопроса администратору {admin_id}")
            except Exception as e2:
                logging.error(f"Не удалось отправить даже текст администратору {admin_id}: {e2}")
    
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