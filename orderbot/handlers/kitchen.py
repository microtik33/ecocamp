from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from ..services.kitchen import get_orders_summary
from ..services.sheets import is_user_cook, get_orders_sheet
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
    
    # Добавляем сообщение с кнопками для поиска заказов
    search_message = "Найти заказы"
    keyboard = [
        [
            InlineKeyboardButton("По комнате", callback_data="search_by_room"),
            InlineKeyboardButton("По номеру", callback_data="search_by_number")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(search_message, reply_markup=reply_markup)

@require_auth
async def search_orders_by_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список комнат для поиска заказов."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Формируем клавиатуру с номерами комнат
    keyboard = [
        [InlineKeyboardButton(f"{i}", callback_data=f"find_room:{i}") for i in range(1, 6)],
        [InlineKeyboardButton(f"{i}", callback_data=f"find_room:{i}") for i in range(6, 11)],
        [InlineKeyboardButton(f"{i}", callback_data=f"find_room:{i}") for i in range(11, 16)],
        [InlineKeyboardButton(f"{i}", callback_data=f"find_room:{i}") for i in range(16, 21)],
        [InlineKeyboardButton("Назад", callback_data="back_to_kitchen")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Выберите номер комнаты:", reply_markup=reply_markup)

@require_auth
async def search_orders_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает запрос на ввод номера заказа."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Сохраняем состояние, что ожидаем ввод номера заказа
    context.user_data['awaiting_order_number'] = True
    
    # Добавляем кнопку "Назад"
    keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_kitchen")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("Введите номер заказа:", reply_markup=reply_markup)

@require_auth
async def handle_order_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод номера заказа."""
    # Проверяем, ожидаем ли ввод номера заказа
    if not context.user_data.get('awaiting_order_number'):
        return
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await update.message.reply_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем введенный номер заказа
    order_number = update.message.text.strip()
    
    # Сбрасываем флаг ожидания ввода
    context.user_data['awaiting_order_number'] = False
    
    # Ищем заказ по номеру
    try:
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        order_found = None
        
        for order in all_orders[1:]:  # Пропускаем заголовок
            if order[0] == order_number:
                order_found = order
                break
        
        if order_found:
            # Формируем сообщение с информацией о заказе
            message = f"📋 Информация о заказе №{order_found[0]}:\n\n"
            message += f"🏠 Номер комнаты: {order_found[6]}\n"
            message += f"👤 Имя: {order_found[7]}\n"
            message += f"🍽 Время дня: {translations.get_meal_type(order_found[8])}\n"
            message += f"🍲 Блюда: {order_found[9]}\n"
            message += f"📝 Пожелания: {order_found[10]}\n"
            message += f"📅 Дата выдачи: {order_found[11]}\n"
            message += f"⏰ Статус: {order_found[2]}\n"
            message += f"📨 Время заказа: {order_found[1]}"
            
            # Добавляем кнопку "Назад к поиску"
            keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(message, reply_markup=reply_markup)
        else:
            # Если заказ не найден
            keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Заказ с номером {order_number} не найден.", reply_markup=reply_markup)
    
    except Exception as e:
        keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Ошибка при поиске заказа: {e}", reply_markup=reply_markup)

@require_auth
async def find_orders_by_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Находит заказы по номеру комнаты."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Получаем номер комнаты из callback_data
    room_number = query.data.split(':')[1]
    
    try:
        # Ищем заказы по комнате
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        room_orders = [order for order in all_orders[1:] if order[6] == room_number]
        
        if room_orders:
            # Формируем сообщение со списком заказов
            message = f"📋 Заказы для комнаты {room_number}:\n\n"
            
            for order in room_orders:
                message += f"🔢 Заказ №{order[0]}\n"
                message += f"👤 Имя: {order[7]}\n"
                message += f"🍽 Время дня: {translations.get_meal_type(order[8])}\n"
                message += f"🍲 Блюда: {order[9]}\n"
                message += f"📅 Дата выдачи: {order[11]}\n"
                message += f"⏰ Статус: {order[2]}\n"
                message += "─" * 30 + "\n"
            
            # Добавляем кнопку "Назад к списку комнат"
            keyboard = [[InlineKeyboardButton("Назад к списку комнат", callback_data="search_by_room")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup)
        else:
            # Если заказы не найдены
            keyboard = [[InlineKeyboardButton("Назад к списку комнат", callback_data="search_by_room")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Заказы для комнаты {room_number} не найдены.", reply_markup=reply_markup)
    
    except Exception as e:
        keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Ошибка при поиске заказов: {e}", reply_markup=reply_markup)

@require_auth
async def back_to_kitchen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возвращает пользователя к поиску заказов."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(str(update.effective_user.id)):
        await query.edit_message_text("У вас нет доступа к этой функции.")
        return
    
    # Возвращаем сообщение с кнопками для поиска заказов
    search_message = "Найти заказы"
    keyboard = [
        [
            InlineKeyboardButton("По комнате", callback_data="search_by_room"),
            InlineKeyboardButton("По номеру", callback_data="search_by_number")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(search_message, reply_markup=reply_markup) 