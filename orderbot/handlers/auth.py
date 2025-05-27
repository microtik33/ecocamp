from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from .. import translations
from ..services.sheets import is_user_authorized, check_phone, save_user_id, is_user_cook, is_user_admin
from ..services.user import update_user_info
from .states import PHONE, MENU

async def setup_commands_for_user(bot, user_id=None, is_cook=False, is_admin=False):
    """Устанавливает доступные команды для пользователя в меню команд.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя (опционально)
        is_cook: Является ли пользователь поваром
        is_admin: Является ли пользователь администратором
    """
    base_commands = [
        BotCommand("new", "новый заказ"),
        BotCommand("menu", "меню на завтра"),
        BotCommand("today", "меню на сегодня"),
        BotCommand("myorders", "мои заказы"),
        BotCommand("ask", "задать вопрос"),
        BotCommand("start", "перезапустить бота")
    ]
    
    # Добавляем команды для поваров
    if is_cook:
        cook_commands = [
            BotCommand("kitchen", "Сводка для кухни"),
            BotCommand("update", "Обновить кэши меню")
        ]
        base_commands.extend(cook_commands)
    
    # Добавляем команды для администраторов
    if is_admin:
        admin_commands = [
            BotCommand("kitchen", "Сводка для кухни"),
            BotCommand("update", "Обновить кэши меню"),
            BotCommand("recount", "Пересчитать учёт заказов за последние 3 дня"),
            BotCommand("stats", "Статистика производительности"),
            BotCommand("clearstats", "Очистить статистику производительности")
        ]
        base_commands.extend(admin_commands)
    
    # Если пользователь указан, устанавливаем команды только для этого пользователя
    if user_id:
        await bot.set_my_commands(base_commands, scope=BotCommandScopeChat(chat_id=user_id))
    else:
        # Иначе устанавливаем общие команды для всех пользователей
        await bot.set_my_commands(base_commands, scope=BotCommandScopeDefault())

async def start(update, context):
    """Начало работы с ботом."""
    user_id = str(update.effective_user.id)
    
    # Обновляем информацию о пользователе
    await update_user_info(update.effective_user)
    
    # Проверяем, авторизован ли пользователь
    if is_user_authorized(user_id):
        # Если пользователь уже авторизован, обновляем список команд
        is_cook = is_user_cook(user_id)
        is_admin = is_user_admin(user_id)
        await setup_commands_for_user(context.bot, int(user_id), is_cook, is_admin)
        
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
            
            # Проверяем, является ли пользователь администратором
            is_admin = is_user_admin(user_id)
            
            # Устанавливаем команды для пользователя в зависимости от его роли
            await setup_commands_for_user(context.bot, int(user_id), is_cook, is_admin)
            
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