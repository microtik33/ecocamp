from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from .. import translations
from ..services.sheets import is_user_authorized, check_phone, save_user_id, is_user_cook
from ..services.user import update_user_info
from .states import PHONE, MENU
from ..main import setup_commands_for_user

async def start(update, context):
    """Начало работы с ботом."""
    user_id = str(update.effective_user.id)
    
    # Обновляем информацию о пользователе
    await update_user_info(update.effective_user)
    
    # Проверяем, авторизован ли пользователь
    if is_user_authorized(user_id):
        # Если пользователь уже авторизован, показываем основное меню
        keyboard = [
            [InlineKeyboardButton(translations.get_button('make_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('tomorrow_menu'), callback_data='tomorrow_menu')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(translations.get_message('welcome'), reply_markup=reply_markup)
        return MENU
    
    # Если пользователь не авторизован, запрашиваем номер телефона
    keyboard = [[KeyboardButton(translations.get_button('share_phone'), request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(translations.get_message('phone_request'), reply_markup=reply_markup)
    return PHONE

async def handle_phone(update, context):
    """Обработка получения номера телефона."""
    # Получаем номер телефона из контакта
    if not update.message.contact:
        await update.message.reply_text(translations.get_message('phone_request'))
        return PHONE
    
    # Получаем номер и убираем "+" если он есть
    phone = update.message.contact.phone_number
    if phone.startswith('+'):
        phone = phone[1:]
    
    # Проверяем номер телефона
    if check_phone(phone):
        # Сохраняем user_id
        user_id = str(update.effective_user.id)
        if save_user_id(phone, user_id):
            # Обновляем информацию о пользователе
            await update_user_info(update.effective_user)
            
            # Удаляем клавиатуру с кнопкой запроса телефона
            keyboard = [[KeyboardButton(translations.get_button('share_phone'), request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(translations.get_message('auth_success'), reply_markup=ReplyKeyboardRemove())
            
            # Проверяем, является ли пользователь поваром
            is_cook = is_user_cook(user_id)
            
            # Устанавливаем команды для пользователя в зависимости от его роли
            await setup_commands_for_user(context.bot, int(user_id), is_cook)
            
            # Показываем основное меню
            keyboard = [
                [InlineKeyboardButton(translations.get_button('make_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('tomorrow_menu'), callback_data='tomorrow_menu')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(translations.get_message('welcome'), reply_markup=reply_markup)
            return MENU
    
    # Если номер не найден или произошла ошибка
    await update.message.reply_text(translations.get_message('auth_failed'))
    return PHONE 