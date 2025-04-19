from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from ..services.kitchen import get_orders_summary
from ..services.sheets import is_user_cook, get_orders_sheet
from .. import translations
from ..utils.auth_decorator import require_auth
from datetime import datetime

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
            # Получаем текущую дату
            today = datetime.now().date()
            is_today_order = False
            
            # Проверяем, является ли заказ на сегодня
            if order_found[11]:
                try:
                    delivery_date = datetime.strptime(order_found[11], "%d.%m.%y").date()
                    is_today_order = (delivery_date == today)
                except ValueError:
                    is_today_order = False
            
            # Проверяем статус заказа
            is_accepted = order_found[2] == 'Принят'
            is_cancelled = order_found[2] == 'Отменён'
            
            # Добавляем красный эмодзи для отмененных заказов
            status_emoji = "🔴" if is_cancelled else ""
            
            # Формируем сообщение с информацией о заказе в новом формате
            message = f"Заказ №{order_found[0]}\n\n"
            message += f"Статус: {status_emoji} {order_found[2]}\n\n"
            message += f"Комната: {order_found[6]}\n"
            message += f"Имя: {order_found[7]}\n"
            message += f"Время дня: {translations.get_meal_type(order_found[8])}\n"
            
            # Подготавливаем блюда для отображения
            dishes_list = []
            if order_found[9]:
                dishes = order_found[9].split(',')
                dishes_text = "Блюда:\n"
                for dish in dishes:
                    dish = dish.strip()
                    dishes_text += f"- {dish}\n"
                dishes_list.append(dishes_text)
            else:
                dishes_list.append("Блюда: -\n")
            
            # Добавляем пожелания и дату выдачи
            additional_info = f"Пожелания: {order_found[10] if order_found[10] and order_found[10] != '—' else '-'}\n"
            additional_info += f"Дата выдачи: {order_found[11]}\n\n"
            additional_info += f"Время заказа: {order_found[1]}"
            
            # Добавляем информацию, относится ли заказ к текущей сводке
            if not is_today_order:
                additional_info += "\n\n⚠️ Этот заказ НЕ на сегодня, и не включен в текущую сводку."
            elif not is_accepted:
                additional_info += "\n\n⚠️ Этот заказ НЕ имеет статус 'Принят', и не включен в текущую сводку."
            
            # Максимальная длина сообщения в Telegram
            MAX_MESSAGE_LENGTH = 4000
            
            # Проверяем общую длину сообщения
            dishes_total_length = sum(len(dish) for dish in dishes_list)
            
            if len(message) + dishes_total_length + len(additional_info) > MAX_MESSAGE_LENGTH:
                # Если всё сообщение слишком длинное, разбиваем на части
                
                # Отправляем первую часть сообщения
                first_message = message
                await update.message.reply_text(first_message)
                
                # Отправляем списки блюд частями
                current_dishes = "Блюда:\n"
                dishes = order_found[9].split(',')
                
                for i, dish in enumerate(dishes):
                    dish = dish.strip()
                    dish_line = f"- {dish}\n"
                    
                    if len(current_dishes) + len(dish_line) > MAX_MESSAGE_LENGTH:
                        await update.message.reply_text(current_dishes)
                        current_dishes = "Блюда (продолжение):\n" + dish_line
                    else:
                        current_dishes += dish_line
                
                if current_dishes and current_dishes != "Блюда:\n" and current_dishes != "Блюда (продолжение):\n":
                    await update.message.reply_text(current_dishes)
                
                # Отправляем дополнительную информацию
                keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(additional_info, reply_markup=reply_markup)
            else:
                # Если сообщение нормальной длины, отправляем всё вместе
                complete_message = message + dishes_list[0] + additional_info
                
                # Добавляем кнопку "Назад к поиску"
                keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(complete_message, reply_markup=reply_markup)
        else:
            # Если заказ не найден
            keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Заказ с номером {order_number} не найден.", reply_markup=reply_markup)
    
    except Exception as e:
        keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Ошибка при поиске заказа: {e}", reply_markup=reply_markup)
        # Логирование ошибки для отладки
        print(f"Ошибка при поиске заказа номер {order_number}: {e}")

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
        
        # Получаем текущую дату
        today = datetime.now().date()
        
        # Фильтруем заказы: только те, что на сегодня и со статусом "Принят"
        room_orders = []
        for order in all_orders[1:]:
            if order[6] == room_number and order[2] == 'Принят' and order[11]:
                try:
                    delivery_date = datetime.strptime(order[11], "%d.%m.%y").date()
                    if delivery_date == today:
                        room_orders.append(order)
                except ValueError:
                    # Если дата в неправильном формате, пропускаем
                    continue
        
        if room_orders:
            # Формируем заголовок для сообщений
            header = f"📋 Заказы для комнаты {room_number} на сегодня ({today.strftime('%d.%m.%Y')}):\n\n"
            
            # Создаем список сообщений
            messages = []
            current_message = header
            
            # Максимальная длина сообщения в Telegram
            MAX_MESSAGE_LENGTH = 4000
            
            # Формируем сообщения с заказами
            for order in room_orders:
                order_text = f"🔢 Заказ №{order[0]}\n"
                order_text += f"👤 Имя: {order[7]}\n"
                order_text += f"🍽 Время дня: {translations.get_meal_type(order[8])}\n"
                order_text += f"🍲 Блюда: {order[9]}\n"
                order_text += f"📝 Пожелания: {order[10] if order[10] and order[10] != '—' else '-'}\n"
                order_text += f"⏰ Статус: {order[2]}\n"
                order_text += "─" * 30 + "\n"
                
                # Проверяем, поместится ли заказ в текущее сообщение
                if len(current_message) + len(order_text) > MAX_MESSAGE_LENGTH:
                    # Если не поместится, добавляем текущее сообщение в список и начинаем новое
                    messages.append(current_message)
                    current_message = header + order_text
                else:
                    # Если поместится, добавляем заказ к текущему сообщению
                    current_message += order_text
            
            # Добавляем последнее сообщение в список
            if current_message and current_message != header:
                messages.append(current_message)
            
            # Отправляем сообщения
            if messages:
                # Отправляем первое сообщение, заменяя текущее
                keyboard = [[InlineKeyboardButton("Назад к списку комнат", callback_data="search_by_room")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(messages[0], reply_markup=reply_markup)
                
                # Отправляем остальные сообщения, если они есть
                for i in range(1, len(messages)):
                    if i == len(messages) - 1:
                        # К последнему сообщению добавляем кнопку
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=messages[i],
                            reply_markup=reply_markup
                        )
                    else:
                        # Промежуточные сообщения без кнопок
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=messages[i]
                        )
        else:
            # Если заказы не найдены
            keyboard = [[InlineKeyboardButton("Назад к списку комнат", callback_data="search_by_room")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"Заказы для комнаты {room_number} на сегодня не найдены.", reply_markup=reply_markup)
    
    except Exception as e:
        keyboard = [[InlineKeyboardButton("Назад к поиску", callback_data="back_to_kitchen")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Ошибка при поиске заказов: {e}", reply_markup=reply_markup)
        # Логирование ошибки для отладки
        print(f"Ошибка при поиске заказов по комнате {room_number}: {e}")

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