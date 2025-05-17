import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import logging
from .. import translations
from ..services.sheets import get_orders_sheet, is_user_authorized
from ..services.user import update_user_stats, get_user_data
from ..utils.auth_decorator import require_auth
from .states import MENU, EDIT_ORDER
from typing import List, Dict, Optional
from ..utils.profiler import profile_time
from ..utils.markdown_utils import escape_markdown_v2
from .order import get_order_info, show_order_form, ask_meal_type, process_order_save

# Настройка логгера
logger = logging.getLogger(__name__)

@profile_time
@require_auth
async def show_user_orders(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ заказов пользователя."""
    # Определяем, как была вызвана функция - через команду или через кнопку
    is_command = bool(update.message)
    
    if not is_command:
        query = update.callback_query
        await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Инициализируем состояние MENU, если оно не установлено
    if 'state' not in context.user_data:
        context.user_data['state'] = MENU
    
    # Получаем дату на завтрашний день
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%y")
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    
    # Фильтруем заказы пользователя со статусами "Активен" и "Оплачен" на завтрашний день
    user_orders = [
        row for row in all_orders[1:] 
        if row[3] == user_id and 
           row[2] in ['Активен', 'Оплачен'] and 
           row[11] == tomorrow_date  # Проверяем дату выдачи на завтра
    ]
    
    if not user_orders:
        message = escape_markdown_v2(translations.get_message('no_active_orders'))
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('today_orders'), callback_data='today_orders')],
            [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
            [InlineKeyboardButton(translations.get_button('paid_orders'), callback_data='paid_orders')],
            [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_command:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Сортируем активные заказы по типу еды: Завтрак - Обед - Ужин
        def meal_type_priority(meal_type):
            if meal_type == 'Завтрак':
                return 0
            elif meal_type == 'Обед':
                return 1
            elif meal_type == 'Ужин':
                return 2
            return 3  # Для других значений
            
        user_orders.sort(key=lambda x: meal_type_priority(x[8]))
        
        messages = []
        current_message = ""
        
        # Добавляем активные заказы
        messages.append(escape_markdown_v2("Ваши заказы на завтра:"))
        for order in user_orders:
            # Формируем информацию о заказе
            delivery_date = order[11] if order[11] else None
            meal_type = order[8]
            meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
            
            # Экранируем специальные символы для Markdown V2
            escaped_order_id = escape_markdown_v2(order[0])
            escaped_status = escape_markdown_v2(order[2])
            escaped_timestamp = escape_markdown_v2(order[1])
            escaped_room = escape_markdown_v2(order[6])
            escaped_name = escape_markdown_v2(order[7])
            escaped_meal_type = escape_markdown_v2(meal_type_with_date)
            
            # Выбираем эмодзи в зависимости от статуса
            status_emoji = "✏️"  # По умолчанию для "Активен"
            if order[2] == 'Оплачен':
                status_emoji = "✅"
            
            order_info = (
                f"{status_emoji} Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                f"🍽 Время дня: {escaped_meal_type}\n"
                f"🍲 Блюда:\n"
            )
            
            # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
            dishes = order[9].split(', ')
            
            # Получаем количества, если они доступны
            has_quantities = False
            quantities = {}
            
            # Проверяем, есть ли дополнительная колонка с количествами (12-я колонка)
            if len(order) > 12 and order[12]:
                try:
                    # Парсим JSON строку с количествами
                    import json
                    quantities = json.loads(order[12].replace("'", '"'))
                    has_quantities = True
                except Exception as e:
                    logger.error(f"Ошибка при парсинге количеств блюд: {e}")
            
            for dish in dishes:
                escaped_dish = escape_markdown_v2(dish)
                quantity = quantities.get(dish, 1) if has_quantities else 1
                order_info += f"  • {escaped_dish} x{quantity}\n"
            
            escaped_wishes = escape_markdown_v2(order[10])
            order_info += f"📝 Пожелания: {escaped_wishes}\n"
            
            order_sum = int(float(order[5])) if order[5] else 0
            escaped_sum = escape_markdown_v2(str(order_sum))
            order_info += f"💰 Сумма заказа: {escaped_sum} р\\.\n"
            order_info += translations.get_message('active_orders_separator')
            
            # Если текущее сообщение станет слишком длинным, начинаем новое
            if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                messages.append(current_message)
                current_message = order_info
            else:
                current_message += order_info
        
        # Добавляем последнее сообщение со списком заказов, если оно есть
        if current_message:
            messages.append(current_message)
        
        # Логирование для отладки
        logger.info(f"Всего найдено заказов на завтра: {len(user_orders)}")
        
        try:
            if len(messages) == 1:
                # Если все помещается в одно сообщение
                message = messages[0]
                if is_command:
                    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.callback_query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                # Отправляем первое сообщение
                if is_command:
                    await update.message.reply_text(messages[0], parse_mode=ParseMode.MARKDOWN_V2)
                else:
                    await update.callback_query.edit_message_text(messages[0], parse_mode=ParseMode.MARKDOWN_V2)
                
                # Отправляем промежуточные сообщения без кнопок
                for msg in messages[1:]:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=msg,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            
            # Отправляем отдельное сообщение с кнопками
            keyboard = [
                [InlineKeyboardButton(translations.get_button('edit_active_orders'), callback_data='edit_active_orders')],                
                [InlineKeyboardButton(translations.get_button('today_orders'), callback_data='today_orders')],
                [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
                [InlineKeyboardButton(translations.get_button('paid_orders'), callback_data='paid_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations.get_message('what_next'),
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке списка заказов: {e}")
            logger.exception("Подробная информация об ошибке:")
            error_message = translations.get_message('orders_display_error')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('edit_active_orders'), callback_data='edit_active_orders')],                
                [InlineKeyboardButton(translations.get_button('today_orders'), callback_data='today_orders')],
                [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
                [InlineKeyboardButton(translations.get_button('paid_orders'), callback_data='paid_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if is_command:
                await update.message.reply_text(error_message, reply_markup=reply_markup)
            else:
                await update.callback_query.edit_message_text(error_message, reply_markup=reply_markup)
    
    # Устанавливаем состояние MENU для обработки кнопок
    context.user_data['state'] = MENU
    return MENU

@profile_time
@require_auth
async def show_today_orders(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ заказов на сегодня со статусами "Принят", "Ожидает оплаты", "Оплачен"."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Инициализируем состояние MENU, если оно не установлено
    if 'state' not in context.user_data:
        context.user_data['state'] = MENU
    
    # Получаем текущую дату в формате "ДД.ММ.ГГ"
    today_date = datetime.now()
    today_date_str = today_date.strftime("%d.%m.%y")
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    
    # Фильтруем заказы пользователя на сегодняшний день со статусами "Принят", "Ожидает оплаты", "Оплачен"
    today_orders = [
        row for row in all_orders[1:] 
        if row[3] == user_id and 
           row[2] in ['Принят', 'Ожидает оплаты', 'Оплачен'] and 
           row[11] == today_date_str  # Проверяем дату выдачи
    ]
    
    if not today_orders:
        message = escape_markdown_v2("У вас нет заказов на сегодня.")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Сортируем заказы по типу еды: Завтрак - Обед - Ужин
        def meal_type_priority(meal_type):
            if meal_type == 'Завтрак':
                return 0
            elif meal_type == 'Обед':
                return 1
            elif meal_type == 'Ужин':
                return 2
            return 3  # Для других значений
            
        today_orders.sort(key=lambda x: meal_type_priority(x[8]))
        
        messages = []
        current_message = ""
        
        # Добавляем заголовок
        messages.append(escape_markdown_v2("Ваши заказы на сегодня:"))
        
        for order in today_orders:
            # Формируем информацию о заказе
            delivery_date = order[11] if order[11] else None
            meal_type = order[8]
            meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
            
            # Экранируем специальные символы для Markdown V2
            escaped_order_id = escape_markdown_v2(order[0])
            escaped_status = escape_markdown_v2(order[2])
            escaped_room = escape_markdown_v2(order[6])
            escaped_name = escape_markdown_v2(order[7])
            escaped_meal_type = escape_markdown_v2(meal_type_with_date)
            
            # Выбираем эмодзи в зависимости от статуса
            status_emoji = "✅"  # По умолчанию для "Оплачен"
            if order[2] == 'Принят':
                status_emoji = "🛎"
            elif order[2] == 'Ожидает оплаты':
                status_emoji = "💸"
            
            order_info = (
                f"{status_emoji} Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                f"🏠 Комната: {escaped_room}\n"
                f"👤 Имя: {escaped_name}\n"
                f"🍽 Время дня: {escaped_meal_type}\n"
                f"🍲 Блюда:\n"
            )
            
            # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
            dishes = order[9].split(', ')
            
            # Получаем количества, если они доступны
            has_quantities = False
            quantities = {}
            
            # Проверяем, есть ли дополнительная колонка с количествами (12-я колонка)
            if len(order) > 12 and order[12]:
                try:
                    # Парсим JSON строку с количествами
                    import json
                    quantities = json.loads(order[12].replace("'", '"'))
                    has_quantities = True
                except Exception as e:
                    logger.error(f"Ошибка при парсинге количеств блюд: {e}")
            
            for dish in dishes:
                escaped_dish = escape_markdown_v2(dish)
                quantity = quantities.get(dish, 1) if has_quantities else 1
                order_info += f"  • {escaped_dish} x{quantity}\n"
            
            escaped_wishes = escape_markdown_v2(order[10])
            order_info += f"📝 Пожелания: {escaped_wishes}\n"
            
            order_sum = int(float(order[5])) if order[5] else 0
            escaped_sum = escape_markdown_v2(str(order_sum))
            order_info += f"💰 Сумма заказа: {escaped_sum} р\\.\n"
            order_info += translations.get_message('active_orders_separator')
            
            # Если текущее сообщение станет слишком длинным, начинаем новое
            if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                messages.append(current_message)
                current_message = order_info
            else:
                current_message += order_info
        
        # Добавляем последнее сообщение со списком заказов, если оно есть
        if current_message:
            messages.append(current_message)
        
        # Логирование для отладки
        logger.info(f"Всего найдено заказов на сегодня: {len(today_orders)}")
        
        try:
            # Отправляем первое сообщение
            await query.edit_message_text(messages[0], parse_mode=ParseMode.MARKDOWN_V2)
            
            # Отправляем дополнительные сообщения
            for msg in messages[1:]:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            
            # Отправляем отдельное сообщение с кнопками
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations.get_message('what_next'),
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке списка заказов на сегодня: {e}")
            logger.exception("Подробная информация об ошибке:")
            error_message = translations.get_message('orders_display_error')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(error_message, reply_markup=reply_markup)
    
    # Устанавливаем состояние MENU для обработки кнопок
    context.user_data['state'] = MENU
    return MENU

@profile_time
@require_auth
async def show_orders_to_pay(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ заказов, ожидающих оплаты и принятых."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Инициализируем состояние MENU, если оно не установлено
    if 'state' not in context.user_data:
        context.user_data['state'] = MENU
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    # Фильтруем заказы пользователя со статусами "Принят" и "Ожидает оплаты"
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Принят', 'Ожидает оплаты']]
    
    if not user_orders:
        message = escape_markdown_v2("У вас нет заказов на оплату.")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Сортируем заказы по приоритету статуса и времени
        # Приоритет: "Ожидает оплаты", "Принят"
        def order_status_priority(status):
            if status == 'Ожидает оплаты':
                return 0
            elif status == 'Принят':
                return 1
            return 2  # Для других значений
        
        user_orders.sort(key=lambda x: (order_status_priority(x[2]), x[1]))
        
        # Разделяем заказы по статусам
        awaiting_payment_orders = [order for order in user_orders if order[2] == 'Ожидает оплаты']
        processing_orders = [order for order in user_orders if order[2] == 'Принят']
        
        messages = []
        current_message = ""
        total_sum = 0
        
        # Добавляем заказы, ожидающие оплаты
        if awaiting_payment_orders:
            messages.append(escape_markdown_v2("Приготовленные заказы, ожидающие оплаты:"))
            for order in awaiting_payment_orders:
                # Формируем информацию о заказе
                delivery_date = order[11] if order[11] else None
                meal_type = order[8]
                meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
                
                # Экранируем специальные символы для Markdown V2
                escaped_order_id = escape_markdown_v2(order[0])
                escaped_status = escape_markdown_v2(order[2])
                escaped_timestamp = escape_markdown_v2(order[1])
                escaped_room = escape_markdown_v2(order[6])
                escaped_name = escape_markdown_v2(order[7])
                escaped_meal_type = escape_markdown_v2(meal_type_with_date)
                
                order_info = (
                    f"💸 Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                    f"🍽 Время дня: {escaped_meal_type}\n"
                    f"🍲 Блюда:\n"
                )
                
                # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
                dishes = order[9].split(', ')
                for dish in dishes:
                    escaped_dish = escape_markdown_v2(dish)
                    order_info += f"  • {escaped_dish}\n"
                
                escaped_wishes = escape_markdown_v2(order[10])
                order_info += f"📝 Пожелания: {escaped_wishes}\n"
                
                order_sum = int(float(order[5])) if order[5] else 0
                total_sum += order_sum
                escaped_sum = escape_markdown_v2(str(order_sum))
                order_info += f"💰 Сумма заказа: {escaped_sum} р\\.\n"
                order_info += translations.get_message('active_orders_separator')
                
                # Если текущее сообщение станет слишком длинным, начинаем новое
                if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                    messages.append(current_message)
                    current_message = order_info
                else:
                    current_message += order_info
        
        # Добавляем заказы в обработке
        if processing_orders:
            if current_message:  # Если есть предыдущие сообщения, добавляем разделитель
                messages.append(current_message)
                current_message = ""
            
            messages.append(escape_markdown_v2("Принятые заказы, переданные повару:"))
            for order in processing_orders:
                # Формируем информацию о заказе
                delivery_date = order[11] if order[11] else None
                meal_type = order[8]
                meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
                
                # Экранируем специальные символы для Markdown V2
                escaped_order_id = escape_markdown_v2(order[0])
                escaped_status = escape_markdown_v2(order[2])
                escaped_timestamp = escape_markdown_v2(order[1])
                escaped_room = escape_markdown_v2(order[6])
                escaped_name = escape_markdown_v2(order[7])
                escaped_meal_type = escape_markdown_v2(meal_type_with_date)
                
                order_info = (
                    f"🛎 Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                    f"🍽 Время дня: {escaped_meal_type}\n"
                    f"🍲 Блюда:\n"
                )
                
                # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
                dishes = order[9].split(', ')
                for dish in dishes:
                    escaped_dish = escape_markdown_v2(dish)
                    order_info += f"  • {escaped_dish}\n"
                
                escaped_wishes = escape_markdown_v2(order[10])
                order_info += f"📝 Пожелания: {escaped_wishes}\n"
                
                order_sum = int(float(order[5])) if order[5] else 0
                total_sum += order_sum
                escaped_sum = escape_markdown_v2(str(order_sum))
                order_info += f"💰 Сумма заказа: {escaped_sum} р\\.\n"
                order_info += translations.get_message('active_orders_separator')
                
                # Если текущее сообщение станет слишком длинным, начинаем новое
                if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                    messages.append(current_message)
                    current_message = order_info
                else:
                    current_message += order_info
        
        # Добавляем последнее сообщение со списком заказов, если оно есть
        if current_message:
            messages.append(current_message)
        
        # Добавляем общую сумму в последнее сообщение
        escaped_total_sum = escape_markdown_v2(str(total_sum))
        total_sum_message = translations.get_message('total_sum', sum=escaped_total_sum)
        
        # Логирование для отладки
        logger.info(f"Итоговая сумма заказов на оплату: {total_sum}, экранированная: {escaped_total_sum}")
        logger.info(f"Сообщение о сумме: {total_sum_message}")
        
        messages[-1] += total_sum_message
        
        try:
            # Отправляем первое сообщение
            await query.edit_message_text(messages[0], parse_mode=ParseMode.MARKDOWN_V2)
            
            # Отправляем дополнительные сообщения
            for msg in messages[1:]:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            
            # Отправляем отдельное сообщение с кнопками
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations.get_message('what_next'),
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке списка заказов на оплату: {e}")
            logger.exception("Подробная информация об ошибке:")
            error_message = translations.get_message('orders_display_error')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(error_message, reply_markup=reply_markup)
    
    # Устанавливаем состояние MENU для обработки кнопок
    context.user_data['state'] = MENU
    return MENU

@profile_time
@require_auth
async def show_paid_orders(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ оплаченных заказов."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Инициализируем состояние MENU, если оно не установлено
    if 'state' not in context.user_data:
        context.user_data['state'] = MENU
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    # Фильтруем заказы пользователя со статусом "Оплачен"
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] == 'Оплачен']
    
    if not user_orders:
        message = escape_markdown_v2("У вас нет оплаченных заказов.")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Сортируем заказы по дате
        user_orders.sort(key=lambda x: x[1], reverse=True)  # Сортировка по времени создания, сначала новые
        
        messages = []
        current_message = ""
        
        # Заголовок
        messages.append(escape_markdown_v2("Ваши оплаченные заказы:"))
        
        # Формируем сообщения для каждого заказа
        for order in user_orders:
            # Формируем информацию о заказе
            delivery_date = order[11] if order[11] else None
            meal_type = order[8]
            meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
            
            # Экранируем специальные символы для Markdown V2
            escaped_order_id = escape_markdown_v2(order[0])
            escaped_status = escape_markdown_v2(order[2])
            escaped_timestamp = escape_markdown_v2(order[1])
            escaped_room = escape_markdown_v2(order[6])
            escaped_name = escape_markdown_v2(order[7])
            escaped_meal_type = escape_markdown_v2(meal_type_with_date)
            
            order_info = (
                f"✅ Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                f"🍽 Время дня: {escaped_meal_type}\n"
                f"🍲 Блюда:\n"
            )
            
            # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
            dishes = order[9].split(', ')
            for dish in dishes:
                escaped_dish = escape_markdown_v2(dish)
                order_info += f"  • {escaped_dish}\n"
            
            escaped_wishes = escape_markdown_v2(order[10])
            order_info += f"📝 Пожелания: {escaped_wishes}\n"
            
            order_sum = int(float(order[5])) if order[5] else 0
            escaped_sum = escape_markdown_v2(str(order_sum))
            order_info += f"💰 Сумма заказа: {escaped_sum} р\\.\n"
            order_info += translations.get_message('active_orders_separator')
            
            # Если текущее сообщение станет слишком длинным, начинаем новое
            if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                messages.append(current_message)
                current_message = order_info
            else:
                current_message += order_info
        
        # Добавляем последнее сообщение со списком заказов, если оно есть
        if current_message:
            messages.append(current_message)
        
        # Логирование для отладки
        logger.info(f"Всего найдено оплаченных заказов: {len(user_orders)}")
        
        try:
            # Отправляем первое сообщение
            await query.edit_message_text(messages[0], parse_mode=ParseMode.MARKDOWN_V2)
            
            # Отправляем дополнительные сообщения
            for msg in messages[1:]:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=msg,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            
            # Отправляем отдельное сообщение с кнопками
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations.get_message('what_next'),
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке списка оплаченных заказов: {e}")
            logger.exception("Подробная информация об ошибке:")
            error_message = translations.get_message('orders_display_error')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('orders_to_pay'), callback_data='orders_to_pay')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(error_message, reply_markup=reply_markup)
    
    # Устанавливаем состояние MENU для обработки кнопок
    context.user_data['state'] = MENU
    return MENU

@require_auth
async def show_edit_active_orders(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ списка активных заказов для редактирования."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Получаем дату на завтрашний день
    tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%y")
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    
    # Фильтруем только активные заказы на завтрашний день
    editable_orders = [
        row for row in all_orders[1:] 
        if row[3] == user_id and 
           row[2] == 'Активен' and 
           row[11] == tomorrow_date  # Проверяем дату выдачи на завтра
    ]
    
    if not editable_orders:
        message = translations.get_message('no_active_orders')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('today_orders'), callback_data='today_orders')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
        return MENU
    
    # Формируем сообщение с вопросом
    message = "Выберите заказ для редактирования:"
    
    # Создаем кнопки для каждого активного заказа
    keyboard = []
    for order in editable_orders:
        # Формируем текст кнопки с информацией о заказе
        delivery_date = order[11] if order[11] else None
        meal_type = order[8]
        meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
        
        button_text = f"Заказ {order[0]} - {meal_type_with_date}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"edit_order:{order[0]}")])
    
    # Добавляем кнопку возврата
    keyboard.append([InlineKeyboardButton(translations.get_button('back'), callback_data="my_orders")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=reply_markup)
    return MENU