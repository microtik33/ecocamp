"""
Обработчик команды /recount для пересчета данных в таблице Rec за последние 3 дня.
"""

from telegram import Update
from telegram.ext import ContextTypes
import logging
from ..services.sheets import is_user_admin
from ..services.records import recount_last_three_days
from ..utils.auth_decorator import require_auth


@require_auth
async def recount_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда для пересчета данных в таблице Rec за последние 3 дня.
    
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
    
    # Отправляем сообщение о начале пересчета
    processing_message = await update.message.reply_text(
        "⏳ Начинаю пересчет данных в таблице Rec за последние 3 дня...\n"
        "Это может занять некоторое время."
    )
    
    try:
        # Выполняем пересчет
        success = await recount_last_three_days()
        
        if success:
            await processing_message.edit_text(
                "✅ Пересчет данных успешно завершен!\n\n"
                "Данные в таблице Rec за последние 3 дня были обновлены."
            )
            logging.info(f"Администратор {user_id} успешно выполнил пересчет данных за последние 3 дня")
        else:
            await processing_message.edit_text(
                "❌ Произошла ошибка при пересчете данных.\n\n"
                "Проверьте логи для получения подробной информации."
            )
            logging.error(f"Ошибка при выполнении пересчета данных администратором {user_id}")
            
    except Exception as e:
        await processing_message.edit_text(
            "❌ Произошла неожиданная ошибка при пересчете данных.\n\n"
            "Обратитесь к разработчику."
        )
        logging.error(f"Неожиданная ошибка при выполнении команды /recount администратором {user_id}: {e}") 