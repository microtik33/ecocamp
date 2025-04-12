from functools import wraps
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from ..services.sheets import is_user_authorized
from ..handlers.auth import start as auth_start
from ..handlers.order import PHONE
from .. import translations

def require_auth(func):
    """Декоратор для проверки аутентификации пользователя."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = str(update.effective_user.id)
        
        if not is_user_authorized(user_id):
            # Если пользователь не авторизован, запрашиваем номер телефона
            keyboard = [[KeyboardButton(translations.get_button('share_phone'), request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(translations.get_message('phone_request'), reply_markup=reply_markup)
            return PHONE
            
        return await func(update, context, *args, **kwargs)
        
    return wrapper 