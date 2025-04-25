import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from datetime import datetime, timedelta, date
import logging
from .. import translations
from ..services import sheets
from ..services.sheets import (
    orders_sheet, get_dishes_for_meal, get_next_order_id, 
    update_user_stats, save_order, update_order, is_user_authorized
)
from ..services.user import update_user_info, update_user_stats
from ..utils.time_utils import is_order_time
from ..utils.auth_decorator import require_auth
from .states import PHONE, MENU, ROOM, NAME, MEAL_TYPE, DISH_SELECTION, WISHES, QUESTION, EDIT_ORDER, PAYMENT
from typing import List, Tuple, Dict, Optional, Any, Union
from ..utils.profiler import profile_time
from ..utils.markdown_utils import escape_markdown_v2

# Настройка логгера
logger = logging.getLogger(__name__)

MAX_DISH_QUANTITY = 20
MIN_DISH_QUANTITY = 1

def get_delivery_date(meal_type: str) -> datetime:
    """Определяет дату выдачи заказа. Все заказы создаются на следующий день."""
    now = datetime.now()
    tomorrow = now.date() + timedelta(days=1)
    return tomorrow

async def show_order_form(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ формы заказа с текущим состоянием."""
    order = context.user_data.get('order', {})
    
    message = "📋 Ваш заказ:\n\n"
    message += f"🏠 Номер комнаты: {order.get('room', '—')}\n"
    message += f"👤 Имя: {order.get('name', '—')}\n"
    
    # Добавляем дату выдачи к типу приема пищи
    meal_type = order.get('meal_type', '—')
    delivery_date = order.get('delivery_date')
    if delivery_date:
        # Если delivery_date уже строка, используем её как есть
        if isinstance(delivery_date, str):
            date_str = delivery_date
        else:
            date_str = delivery_date.strftime("%d.%m")
        message += f"🍽 Время дня: {translations.get_meal_type(meal_type)} ({date_str})\n"
    else:
        message += f"🍽 Время дня: {translations.get_meal_type(meal_type)}\n"
    
    # Формируем список блюд с количеством
    message += "🍲 Блюда:\n"
    if order.get('dishes'):
        for dish in order['dishes']:
            quantity = order['quantities'].get(dish, 1)
            message += f"  • {dish} x{quantity}\n"
    else:
        message += "  —\n"
    
    message += f"📝 Пожелания: {order.get('wishes', '—')}"
    
    if order.get('dishes') and order.get('prices'):
        total = int(sum(float(order['prices'].get(dish, 0)) * order['quantities'].get(dish, 1) 
                       for dish in order['dishes']))
        message += f"\n💰 Сумма заказа: {total} р."
    
    return message

@require_auth
async def handle_order_time_error(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработка попытки сделать заказ в неправильное время."""
    query = update.callback_query
    await query.answer()
    
    message = translations.get_message('wrong_order_time')
    keyboard = [
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text=message, reply_markup=reply_markup)
    return MENU

@profile_time
@require_auth
async def ask_room(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Запрос номера комнаты."""
    query = update.callback_query
    await query.answer()
    
    # Проверяем время для заказа
    if not is_order_time():
        return await handle_order_time_error(update, context)
    
    # Очищаем данные предыдущего заказа, если это не редактирование
    if not context.user_data.get('editing'):
        context.user_data['order'] = {}
    
    # Формируем клавиатуру с номерами комнат
    keyboard = [
        [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(1, 6)],
        [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(6, 11)],
        [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(11, 16)],
        [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(16, 21)],
        [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с формой заказа
    order_message = await show_order_form(update, context)
    sent_message = await query.message.reply_text(order_message)
    context.user_data['order_chat_id'] = sent_message.chat_id
    context.user_data['order_message_id'] = sent_message.message_id
    
    # Отправляем сообщение с выбором комнаты
    await query.message.reply_text(translations.get_message('choose_room'), reply_markup=reply_markup, parse_mode="MarkdownV2")
    await query.message.delete()
    return ROOM

async def ask_name(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Запрос имени."""
    query = update.callback_query
    await query.answer()
    await query.delete_message()
    
    action, value = query.data.split(':')
    if action == 'room':
        if context.user_data.get('editing') and context.user_data['order'].get('room') == value:
            pass
        else:
            context.user_data['order']['room'] = value
    
    context.user_data['state'] = NAME
    
    order_message = await show_order_form(update, context)
    prompt_message = translations.get_message('enter_name')
    
    keyboard = [
        [InlineKeyboardButton(translations.get_button('back'), callback_data="back")],
        [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.edit_message_text(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id'],
            text=order_message
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            # Если сообщение не изменилось, просто пропускаем ошибку
            pass
        else:
            raise e
    
    sent_message = await query.message.reply_text(prompt_message, reply_markup=reply_markup)
    context.user_data['prompt_message_id'] = sent_message.message_id
    return NAME

@profile_time
@require_auth
async def ask_meal_type(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Запрос типа еды."""
    context.user_data['state'] = MEAL_TYPE
    
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['prompt_message_id']
        )
    except Exception as e:
        print(f"Ошибка при удалении сообщения с запросом имени: {e}")
    
    if not isinstance(update, telegram.Update) or not update.message:
        pass
    else:
        if context.user_data.get('editing') and context.user_data['order'].get('name') == update.message.text:
            pass
        else:
            context.user_data['order']['name'] = update.message.text
        await update.message.delete()
    
    order_message = await show_order_form(update, context)
    prompt_message = translations.get_message('choose_meal')
    
    # Получаем даты выдачи для каждого типа приема пищи
    breakfast_date = get_delivery_date('breakfast')
    lunch_date = get_delivery_date('lunch')
    dinner_date = get_delivery_date('dinner')
    
    # Форматируем даты в строки
    date_format = "%d.%m"
    breakfast_str = breakfast_date.strftime(date_format)
    lunch_str = lunch_date.strftime(date_format)
    dinner_str = dinner_date.strftime(date_format)
    
    # Формируем клавиатуру с датами
    keyboard = [
        [
            InlineKeyboardButton(f"{translations.get_button('breakfast')} ({breakfast_str})", 
                               callback_data="meal:Завтрак"),
            InlineKeyboardButton(f"{translations.get_button('lunch')} ({lunch_str})", 
                               callback_data="meal:Обед"),
            InlineKeyboardButton(f"{translations.get_button('dinner')} ({dinner_str})", 
                               callback_data="meal:Ужин")
        ],
        [InlineKeyboardButton(translations.get_button('back'), callback_data="back")],
        [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await context.bot.edit_message_text(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id'],
            text=order_message
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            raise e
    
    if isinstance(update, telegram.Update) and update.message:
        sent_message = await update.message.reply_text(prompt_message, reply_markup=reply_markup)
    else:
        sent_message = await update.callback_query.message.reply_text(prompt_message, reply_markup=reply_markup)
    
    context.user_data['prompt_message_id'] = sent_message.message_id
    return MEAL_TYPE

def _build_dish_keyboard(
    dishes_with_prices: List[Tuple[str, str, str]],
    quantities: Dict[str, int],
    prices: Dict[str, str]
) -> List[List[InlineKeyboardButton]]:
    """
    Создает клавиатуру для выбора блюд.
    
    Args:
        dishes_with_prices: Список кортежей (название_блюда, цена, вес)
        quantities: Словарь количества выбранных блюд
        prices: Словарь цен блюд
    
    Returns:
        List[List[InlineKeyboardButton]]: Клавиатура с кнопками выбора блюд
    """
    keyboard = []
    for dish, price, weight in dishes_with_prices:
        quantity = quantities.get(dish, 0)
        if quantity > 0:
            text = f"✅ {dish} {price} р. ({weight}) ({quantity})"
            keyboard.append([
                InlineKeyboardButton("-", callback_data=f"quantity:{dish}:{max(0, quantity-1)}"),
                InlineKeyboardButton(text, callback_data=f"quantity:{dish}:{quantity}"),
                InlineKeyboardButton("+", callback_data=f"quantity:{dish}:{min(MAX_DISH_QUANTITY, quantity+1)}")
            ])
        else:
            text = f"{dish} {price} р. ({weight})"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"select_dish:{dish}")])
    
    # Добавляем служебные кнопки
    keyboard.append([InlineKeyboardButton(translations.get_button('done'), callback_data="done")])
    keyboard.append([InlineKeyboardButton(translations.get_button('back'), callback_data="back")])
    keyboard.append([InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")])
    
    return keyboard

@profile_time
@require_auth
async def show_dishes(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показывает список доступных блюд и обрабатывает их выбор.
    
    Функция отображает список блюд с ценами и весом, позволяет выбирать блюда
    и изменять их количество. Поддерживает следующие действия:
    - Выбор блюда (добавление в заказ)
    - Изменение количества выбранного блюда
    - Подтверждение выбора (кнопка "Готово")
    - Возврат к предыдущему шагу
    - Отмена заказа
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота с пользовательскими данными
    
    Returns:
        int: Следующее состояние диалога (DISH_SELECTION или WISHES)
    
    Raises:
        telegram.error.BadRequest: При ошибках отправки сообщений
    """
    query = update.callback_query
    await query.answer()
    
    # Проверяем, является ли это кнопкой "done"
    if query.data == "done":
        return await handle_dish_selection(update, context)
    
    # Пытаемся удалить предыдущее сообщение
    try:
        await query.message.delete()
    except telegram.error.BadRequest:
        pass  # Игнорируем ошибку, если сообщение уже удалено
    
    context.user_data['state'] = DISH_SELECTION
    
    # Разбираем callback_data
    try:
        action, value = query.data.split(':', 1)
    except ValueError:
        return DISH_SELECTION
    
    order = context.user_data.get('order', {})
    
    if action == 'meal':
        # Инициализация нового заказа
        order['meal_type'] = value
        order['dishes'] = []
        order['quantities'] = {}
        order['prices'] = {}
        order['delivery_date'] = get_delivery_date(value)
        context.user_data['order'] = order
    
    # Получаем и отображаем текущий статус заказа
    try:
        order_message = await show_order_form(update, context)
        await context.bot.edit_message_text(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id'],
            text=order_message
        )
    except telegram.error.BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Ошибка при обновлении сообщения заказа: {e}")
    
    # Формируем сообщение со списком блюд
    prompt_message = translations.get_message('choose_dishes')
    dishes_with_prices = get_dishes_for_meal(order['meal_type'])
    
    # Создаем клавиатуру
    keyboard = _build_dish_keyboard(
        dishes_with_prices,
        order.get('quantities', {}),
        order.get('prices', {})
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с клавиатурой
    try:
        await query.message.reply_text(prompt_message, reply_markup=reply_markup)
    except telegram.error.BadRequest as e:
        logger.error(f"Ошибка при отправке сообщения с меню: {e}")
        await query.message.reply_text(
            translations.get_message('error_try_again'),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(translations.get_button('back'), callback_data="back")
            ]])
        )
    
    return DISH_SELECTION

@profile_time
@require_auth
async def handle_dish_selection(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработка выбора блюд."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "done":
        if not context.user_data['order'].get('dishes'):
            await query.answer(translations.get_message('no_dishes'), show_alert=True)
            return DISH_SELECTION
        
        try:
            prompt_message = translations.get_message('wishes_prompt')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('no_wishes'), callback_data="wishes:none")],
                [InlineKeyboardButton(translations.get_button('back'), callback_data="back")],
                [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.message.delete()
            
            context.user_data['state'] = WISHES
            
            sent_message = await context.bot.send_message(
                chat_id=context.user_data['order_chat_id'],
                text=prompt_message,
                reply_markup=reply_markup
            )
            context.user_data['prompt_message_id'] = sent_message.message_id
            return WISHES
            
        except Exception as e:
            print(f"Ошибка при обработке кнопки 'Готово': {e}")
            return DISH_SELECTION
    
    action = query.data.split(':', 1)[0]
    order = context.user_data['order']
    
    if action == 'select_dish':
        # Сразу добавляем блюдо с количеством 1
        dish = query.data.split(':', 1)[1]
        order['quantities'][dish] = 1
        if dish not in order['dishes']:
            order['dishes'].append(dish)
            
        # Получаем цену из кэша
        dishes_with_prices = get_dishes_for_meal(order['meal_type'])
        for d, p, w in dishes_with_prices:
            if d == dish:
                order['prices'][dish] = p
                break
        
        # Обновляем отображение формы заказа
        order_message = await show_order_form(update, context)
        await context.bot.edit_message_text(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id'],
            text=order_message
        )
        
        # Показываем обновленный список блюд
        prompt_message = translations.get_message('choose_dishes')
        dishes_with_prices = get_dishes_for_meal(order['meal_type'])
        
        # Формируем клавиатуру
        keyboard = _build_dish_keyboard(
            dishes_with_prices,
            order.get('quantities', {}),
            order.get('prices', {})
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.delete()
        except telegram.error.BadRequest:
            pass
            
        await context.bot.send_message(
            chat_id=context.user_data['order_chat_id'],
            text=prompt_message,
            reply_markup=reply_markup
        )
        return DISH_SELECTION
    
    elif action == 'quantity':
        # Обработка изменения количества
        _, dish, quantity = query.data.split(':')
        quantity = int(quantity)
        
        if quantity <= 0:
            # Удаляем блюдо из заказа
            if dish in order['quantities']:
                del order['quantities'][dish]
            if dish in order['dishes']:
                order['dishes'].remove(dish)
            if dish in order.get('prices', {}):
                del order['prices'][dish]
        else:
            # Обновляем количество
            order['quantities'][dish] = quantity
            
            # Получаем цену из кэша
            if dish not in order.get('prices', {}):
                dishes_with_prices = get_dishes_for_meal(order['meal_type'])
                for d, p, w in dishes_with_prices:
                    if d == dish:
                        order['prices'][dish] = p
                        break
        
        # Обновляем отображение формы заказа
        order_message = await show_order_form(update, context)
        await context.bot.edit_message_text(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id'],
            text=order_message
        )
        
        # Показываем обновленный список блюд
        prompt_message = translations.get_message('choose_dishes')
        dishes_with_prices = get_dishes_for_meal(order['meal_type'])
        
        # Формируем клавиатуру
        keyboard = _build_dish_keyboard(
            dishes_with_prices,
            order.get('quantities', {}),
            order.get('prices', {})
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.delete()
        except telegram.error.BadRequest:
            pass
            
        await context.bot.send_message(
            chat_id=context.user_data['order_chat_id'],
            text=prompt_message,
            reply_markup=reply_markup
        )
        return DISH_SELECTION
    
    return DISH_SELECTION

async def process_order_save(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE, from_message=False):
    """Сохранение заказа."""
    order = context.user_data['order']
    
    # Отправляем промежуточное сообщение
    processing_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⏳ Создаём заказ..."
    )
    
    # Обновляем информацию о пользователе
    await update_user_info(update.effective_user)
    
    if 'timestamp' not in order:
        order['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if 'status' not in order:
        order['status'] = 'Активен'
    if 'user_id' not in order:
        order['user_id'] = str(update.effective_user.id)
    
    if 'order_id' not in order:
        order['order_id'] = get_next_order_id()
    
    # Формируем ссылку на профиль пользователя
    username = update.effective_user.username or '-'
    username_link = f"t.me/{username}" if username != '-' else '-'
    
    # Подсчитываем общую сумму заказа
    total = int(sum(float(order['prices'].get(dish, 0)) * order['quantities'].get(dish, 1) 
                   for dish in order['dishes']))
    
    # Форматируем дату выдачи в нужном формате
    delivery_date = order.get('delivery_date')
    if isinstance(delivery_date, datetime):
        formatted_delivery_date = delivery_date.strftime("%d.%m.%y")
    elif isinstance(delivery_date, date):
        formatted_delivery_date = delivery_date.strftime("%d.%m.%y")
    else:
        formatted_delivery_date = delivery_date
    
    # Форматируем дату создания заказа
    try:
        # Пробуем разные форматы даты
        timestamp = order['timestamp']
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    timestamp = datetime.strptime(timestamp, "%d.%m.%Y %H:%M:%S")
                except ValueError:
                    timestamp = datetime.now()
        formatted_timestamp = timestamp.strftime("%d.%m.%Y %H:%M:%S")
    except Exception as e:
        print(f"Ошибка при форматировании даты: {e}")
        formatted_timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Формируем данные для сохранения
    order_data = {
        'order_id': order['order_id'],
        'timestamp': order['timestamp'],
        'status': order['status'],
        'user_id': order['user_id'],
        'username': username_link,
        'total_price': str(total),  # Преобразуем число в строку для сохранения
        'room': order['room'],
        'name': order['name'],
        'meal_type': order['meal_type'],
        'dishes': order['dishes'],
        'quantities': order.get('quantities', {}),  # Добавляем количества
        'wishes': order.get('wishes', translations.get_message('no_wishes')),
        'delivery_date': formatted_delivery_date
    }
    
    # Сохраняем или обновляем заказ
    success = False
    if not context.user_data.get('editing'):
        success = await save_order(order_data)
    else:
        # Получаем все заказы и ищем нужный для обновления
        from orderbot.services.sheets import get_orders_sheet
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        order_found = False
        
        for idx, row in enumerate(all_orders):
            if (row[0] == order['order_id'] and  # Проверяем ID заказа
                row[2] == 'Активен' and          # Проверяем что заказ активен
                row[3] == order['user_id']):     # Проверяем ID пользователя
                
                try:
                    # Обновляем ячейку с суммой заказа отдельно, чтобы избежать проблем с форматированием
                    orders_sheet.update_cell(idx + 1, 6, float(total))  # Колонка F (индекс 5) содержит сумму заказа
                    success = await update_order(order['order_id'], idx + 1, order_data)
                    order_found = True
                except Exception as e:
                    print(f"Ошибка при обновлении заказа: {e}")
                    success = False
                break
        
        if not order_found:
            print(f"Ошибка: заказ с ID {order['order_id']} не найден или не активен")
            message = translations.get_message('order_not_found')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if from_message:
                await update.message.reply_text(message, reply_markup=reply_markup)
            else:
                await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
            return MENU
    
    if not success:
        message = translations.get_message('order_save_error')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if from_message:
            await update.message.reply_text(message, reply_markup=reply_markup)
        else:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
        return MENU
    
    # Удаляем сообщение с формой заказа
    try:
        await context.bot.delete_message(
            chat_id=context.user_data['order_chat_id'],
            message_id=context.user_data['order_message_id']
        )
    except Exception as e:
        print(f"Ошибка при удалении сообщения: {e}")
    
    # Обновляем статистику пользователя
    await update_user_stats(order['user_id'])
    
    # Формируем сообщение об успешном сохранении
    delivery_date_str = formatted_delivery_date
    meal_type_with_date = f"{translations.get_meal_type(order['meal_type'])} ({delivery_date_str})" if delivery_date_str else translations.get_meal_type(order['meal_type'])
    
    # Формируем список блюд с количеством
    dishes_list = []
    for dish in order['dishes']:
        quantity = order['quantities'].get(dish, 1)
        dishes_list.append(f"  • {dish} x{quantity}")
    dishes_str = '\n'.join(dishes_list)
    
    message = translations.get_message('order_updated' if context.user_data.get('editing') else 'order_created', 
                                     order_id=order['order_id'],
                                     room=order['room'],
                                     name=order['name'],
                                     meal_type=meal_type_with_date,
                                     dishes=f"\n{dishes_str}",  # Добавляем перенос строки перед списком блюд
                                     wishes=order.get('wishes', translations.get_message('no_wishes')),
                                     total=total,
                                     timestamp=formatted_timestamp)  # Используем отформатированную дату
    
    # Добавляем кнопки для дальнейших действий
    keyboard = [
        [InlineKeyboardButton(translations.get_button('edit_order'), callback_data='edit_order')],
        [InlineKeyboardButton(translations.get_button('cancel_order'), callback_data='cancel_order')],
        [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Удаляем промежуточное сообщение
    try:
        await processing_message.delete()
    except Exception as e:
        print(f"Ошибка при удалении промежуточного сообщения: {e}")
    
    # Отправляем сообщение
    if from_message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(message, reply_markup=reply_markup)
    
    context.user_data['editing'] = False
    return MENU

async def handle_text_input(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода."""
    current_state = context.user_data.get('state', NAME)
    
    if current_state == WISHES:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=context.user_data['prompt_message_id']
            )
        except Exception as e:
            print(f"Ошибка при удалении сообщения с запросом пожеланий: {e}")
        
        context.user_data['order']['wishes'] = update.message.text
        await update.message.delete()
        return await process_order_save(update, context, from_message=True)
    
    context.user_data['order']['name'] = update.message.text
    return await ask_meal_type(update, context)

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
    
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    # Фильтруем заказы пользователя со статусами "Принят", "Активен" и "Ожидает оплаты"
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']]
    
    if not user_orders:
        message = escape_markdown_v2(translations.get_message('no_active_orders'))
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_command:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        # Сортируем заказы по приоритету статуса и времени
        # Приоритет: "Ожидает оплаты", "Принят", "Активен"
        def order_status_priority(status):
            if status == 'Ожидает оплаты':
                return 0
            elif status == 'Принят':
                return 1
            else:  # Активен
                return 2
        
        user_orders.sort(key=lambda x: (order_status_priority(x[2]), x[1]))
        
        # Разделяем заказы по статусам
        awaiting_payment_orders = [order for order in user_orders if order[2] == 'Ожидает оплаты']
        processing_orders = [order for order in user_orders if order[2] == 'Принят']
        active_orders = [order for order in user_orders if order[2] == 'Активен']
        
        messages = []
        current_message = ""
        total_sum = 0
        
        # Добавляем заказы, ожидающие оплаты
        if awaiting_payment_orders:
            messages.append(escape_markdown_v2("Ваши заказы, ожидающие оплаты:"))
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
                    f"💰 Заказ *{escaped_order_id}* \\({escaped_status}\\)\n"
                    f"🍽 Время: {escaped_meal_type}\n"
                )
                
                # Разбиваем строку с блюдами на отдельные блюда и форматируем каждое
                dishes = order[9].split(', ')
                for dish in dishes:
                    escaped_dish = escape_markdown_v2(dish)
                    order_info += f"  • {escaped_dish}\n"
                
                order_sum = int(float(order[5])) if order[5] else 0
                total_sum += order_sum
                escaped_sum = escape_markdown_v2(str(order_sum))
                order_info += f"💰 Сумма: {escaped_sum} р\\.\n"
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
            
            messages.append(escape_markdown_v2("Ваши заказы, переданные повару:"))
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
                    f"🍽 Время: {escaped_meal_type}\n"
                )
                order_sum = int(float(order[5])) if order[5] else 0
                total_sum += order_sum
                escaped_sum = escape_markdown_v2(str(order_sum))
                order_info += f"💰 Сумма: {escaped_sum} р\\.\n"
                order_info += translations.get_message('active_orders_separator')
                
                # Если текущее сообщение станет слишком длинным, начинаем новое
                if len(current_message + order_info) > 3000:  # Оставляем запас для доп. текста
                    messages.append(current_message)
                    current_message = order_info
                else:
                    current_message += order_info
        
        # Добавляем активные заказы
        if active_orders:
            if current_message:  # Если есть предыдущие сообщения, добавляем разделитель
                messages.append(current_message)
                current_message = ""
            
            messages.append(escape_markdown_v2("Ваши активные заказы:"))
            for order in active_orders:
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
                    f"⏰ {escaped_timestamp}\n"
                    f"🏠 Комната: {escaped_room}\n"
                    f"👤 Имя: {escaped_name}\n"
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
        logger.info(f"Итоговая сумма: {total_sum}, экранированная: {escaped_total_sum}")
        logger.info(f"Сообщение о сумме: {total_sum_message}")
        
        messages[-1] += total_sum_message
        
        try:
            if not user_orders or len(messages) == 1:
                # Если заказов нет или все помещается в одно сообщение
                message = messages[0] if user_orders else message
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
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('edit_active_orders'), callback_data='edit_active_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
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
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('edit_active_orders'), callback_data='edit_active_orders')],
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

@require_auth
async def cancel_order(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Отмена существующего заказа."""
    query = update.callback_query
    await query.answer()

    order = context.user_data['order']
    user_id = str(update.effective_user.id)
    
    try:
        # Получаем все заказы и ищем нужный для отмены
        from orderbot.services.sheets import get_orders_sheet
        orders_sheet = get_orders_sheet()
        all_orders = orders_sheet.get_all_values()
        order_found = False
        
        for idx, row in enumerate(all_orders):
            if (row[0] == order['order_id'] and  # Проверяем ID заказа
                row[2] in ['Активен', 'Принят', 'Ожидает оплаты'] and  # Проверяем статус
                row[3] == user_id):              # Проверяем ID пользователя
                
                # Меняем статус заказа на "Отменён"
                orders_sheet.update_cell(idx + 1, 3, 'Отменён')
                order_found = True
                break
        
        if not order_found:
            message = translations.get_message('order_cancel_error')
        else:
            # Обновляем статистику пользователя после отмены заказа
            await update_user_stats(user_id)
            message = translations.get_message('order_cancelled')
        
        # Добавляем кнопки для дальнейших действий
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(message, reply_markup=reply_markup)
        context.user_data.clear()
        return MENU
        
    except Exception as e:
        print(f"Ошибка при отмене заказа: {e}")
        message = translations.get_message('order_cancel_error')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
        return MENU

async def get_order_info(order_id: str) -> dict:
    """Получение информации о заказе из таблицы."""
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    for row in all_orders[1:]:  # Пропускаем заголовок
        if row[0] == order_id:
            # Формируем словарь с информацией о заказе
            order_info = {
                'order_id': row[0],
                'timestamp': row[1],
                'status': row[2],
                'user_id': row[3],
                'username': row[4],
                'total_price': row[5],
                'room': row[6],
                'name': row[7],
                'meal_type': row[8],
                'dishes': row[9].split(', ') if row[9] else [],
                'wishes': row[10],
                'delivery_date': row[11]
            }
            return order_info
    return None

async def handle_order_update(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработка всех изменений в заказе."""
    query = update.callback_query
    await query.answer()

    if query.data == 'new_order':
        return await ask_room(update, context)
    
    if query.data.startswith('edit_order:'):
        # Получаем ID заказа из callback_data
        order_id = query.data.split(':')[1]
        
        # Получаем информацию о заказе
        order_info = await get_order_info(order_id)
        
        if not order_info:
            message = translations.get_message('order_not_found')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
            return MENU
        
        # Сохраняем информацию о заказе в контексте
        context.user_data['order'] = order_info
        context.user_data['editing'] = True
        
        # Формируем сообщение с информацией о заказе
        delivery_date = order_info['delivery_date']
        meal_type = order_info['meal_type']
        meal_type_with_date = f"{translations.get_meal_type(meal_type)} ({delivery_date})" if delivery_date else translations.get_meal_type(meal_type)
        
        message = (
            f"📋 Информация о заказе №{order_info['order_id']}:\n\n"
            f"🏠 Номер комнаты: {order_info['room']}\n"
            f"👤 Имя: {order_info['name']}\n"
            f"🍽 Время дня: {meal_type_with_date}\n"
            f"🍲 Блюда:\n"
        )
        
        # Добавляем список блюд
        for dish in order_info['dishes']:
            message += f"  • {dish}\n"
        
        message += f"📝 Пожелания: {order_info['wishes']}\n"
        message += f"💰 Сумма заказа: {order_info['total_price']} р.\n"
        message += f"⏰ Заказ оформлен: {order_info['timestamp']}\n"
        message += f"📊 Статус: {order_info['status']}\n\n"
        message += "Хотите отредактировать этот заказ?"
        
        keyboard = [
            [InlineKeyboardButton(translations.get_button('edit_order'), callback_data="edit_order")],
            [InlineKeyboardButton(translations.get_button('cancel_order'), callback_data="cancel_order")],
            [InlineKeyboardButton(translations.get_button('return_to_list'), callback_data="edit_active_orders")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
        return MENU
    
    if query.data == 'edit_order':
        # Сохраняем полную копию старого заказа
        context.user_data['original_order'] = context.user_data['order'].copy()
        
        # Сохраняем только необходимые данные для идентификации заказа
        old_order = context.user_data['order']
        saved_data = {
            'order_id': old_order['order_id'],
            'timestamp': old_order['timestamp'],
            'status': old_order['status'],
            'user_id': old_order['user_id'],
            'prices': old_order.get('prices', {}),  # Сохраняем цены блюд
            'quantities': old_order.get('quantities', {})  # Сохраняем количества
        }
        
        # Очищаем данные заказа и сохраняем только идентификационную информацию
        context.user_data['order'] = saved_data
        context.user_data['editing'] = True
        
        # Начинаем процесс редактирования с выбора комнаты
        return await ask_room(update, context)
    
    if query.data == 'cancel_order':
        # Получаем информацию о заказе
        order = context.user_data['order']
        user_id = str(update.effective_user.id)
        
        try:
            # Получаем все заказы и ищем нужный для отмены
            from orderbot.services.sheets import get_orders_sheet
            orders_sheet = get_orders_sheet()
            all_orders = orders_sheet.get_all_values()
            order_found = False
            
            for idx, row in enumerate(all_orders):
                if (row[0] == order['order_id'] and  # Проверяем ID заказа
                    row[2] in ['Активен', 'Принят', 'Ожидает оплаты'] and  # Проверяем статус
                    row[3] == user_id):              # Проверяем ID пользователя
                    
                    # Меняем статус заказа на "Отменён"
                    orders_sheet.update_cell(idx + 1, 3, 'Отменён')
                    order_found = True
                    break
            
            if not order_found:
                message = translations.get_message('order_cancel_error')
            else:
                # Обновляем статистику пользователя после отмены заказа
                await update_user_stats(user_id)
                message = translations.get_message('order_cancelled')
            
            # Добавляем кнопки для дальнейших действий
            keyboard = [
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup)
            context.user_data.clear()
            return MENU
            
        except Exception as e:
            print(f"Ошибка при отмене заказа: {e}")
            message = translations.get_message('order_cancel_error')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
            return MENU
    
    if query.data == 'back':
        current_state = context.user_data.get('state', NAME)
        
        # Сохраняем текущий чат и ID сообщения с информацией о заказе
        chat_id = context.user_data['order_chat_id']
        message_id = context.user_data['order_message_id']
        
        # Удаляем текущее сообщение с кнопками
        try:
            await query.message.delete()
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")
        
        # Определяем следующее состояние и отправляем соответствующее сообщение
        if current_state == NAME:
            # Возврат к выбору комнаты
            context.user_data['state'] = ROOM
            keyboard = [
                [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(1, 6)],
                [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(6, 11)],
                [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(11, 16)],
                [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(16, 21)],
                [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id, text=translations.get_message('choose_room'), reply_markup=reply_markup, parse_mode="MarkdownV2")
            return ROOM
            
        elif current_state == MEAL_TYPE:
            # Возврат к вводу имени
            context.user_data['state'] = NAME
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back'), callback_data="back")],
                [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sent_message = await context.bot.send_message(chat_id=chat_id, text=translations.get_message('enter_name'), reply_markup=reply_markup)
            context.user_data['prompt_message_id'] = sent_message.message_id
            return NAME

        elif current_state == DISH_SELECTION:
            # Возврат к выбору типа еды
            context.user_data['state'] = MEAL_TYPE
            
            # Получаем даты выдачи для каждого типа приема пищи
            breakfast_date = get_delivery_date('breakfast')
            lunch_date = get_delivery_date('lunch')
            dinner_date = get_delivery_date('dinner')
            
            # Форматируем даты в строки
            date_format = "%d.%m"
            breakfast_str = breakfast_date.strftime(date_format)
            lunch_str = lunch_date.strftime(date_format)
            dinner_str = dinner_date.strftime(date_format)
            
            keyboard = [
                [
                    InlineKeyboardButton(f"{translations.get_button('breakfast')} ({breakfast_str})", 
                                       callback_data="meal:Завтрак"),
                    InlineKeyboardButton(f"{translations.get_button('lunch')} ({lunch_str})", 
                                       callback_data="meal:Обед"),
                    InlineKeyboardButton(f"{translations.get_button('dinner')} ({dinner_str})", 
                                       callback_data="meal:Ужин")
                ],
                [InlineKeyboardButton(translations.get_button('back'), callback_data="back")],
                [InlineKeyboardButton(translations.get_button('cancel'), callback_data="cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id, text=translations.get_message('choose_meal'), reply_markup=reply_markup)
            return MEAL_TYPE

        elif current_state == WISHES:
            # Возврат к выбору блюд
            context.user_data['state'] = DISH_SELECTION
            order = context.user_data['order']
            keyboard = _build_dish_keyboard(
                get_dishes_for_meal(order['meal_type']),
                order.get('quantities', {}),
                order.get('prices', {})
            )
            await context.bot.send_message(chat_id=chat_id, text=translations.get_message('choose_dishes'), reply_markup=InlineKeyboardMarkup(keyboard))
            return DISH_SELECTION
    
    if query.data == 'cancel':
        # Удаляем информационное сообщение о заказе
        try:
            if context.user_data.get('order_message_id'):
                from orderbot.services.sheets import get_orders_sheet
                orders_sheet = get_orders_sheet()
                orders_sheet.delete_row(context.user_data['order_message_id'])
        except Exception as e:
            print(f"Ошибка при удалении сообщения о заказе: {e}")
            
        if context.user_data.get('editing'):
            # Восстанавливаем оригинальный заказ
            context.user_data['order'] = context.user_data['original_order']
            context.user_data['editing'] = False
            
            # Формируем сообщение о заказе
            message = translations.get_message('edit_cancelled')
            message += await show_order_form(update, context)
            message += translations.get_message('what_next')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('edit_order'), callback_data='edit_order')],
                [InlineKeyboardButton(translations.get_button('cancel_order'), callback_data='cancel_order')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
        else:
            # Полная отмена заказа
            context.user_data.clear()
            message = translations.get_message('new_order_cancelled')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('make_order'), callback_data='new_order')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, reply_markup=reply_markup)
        return MENU
    
    action, value = query.data.split(':')
    if action == 'wishes' and value == 'none':
        context.user_data['order']['wishes'] = translations.get_message('no_wishes')
        return await process_order_save(update, context)
    
    return MENU

@require_auth
async def show_edit_active_orders(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показ списка активных заказов для редактирования."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    # Фильтруем только активные заказы и заказы, ожидающие оплаты
    editable_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Активен', 'Ожидает оплаты']]
    
    if not editable_orders:
        message = translations.get_message('no_active_orders')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
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
        
        # Добавляем статус заказа в текст кнопки
        status_text = " (Ожидает оплаты)" if order[2] == 'Ожидает оплаты' else ""
        button_text = f"Заказ {order[0]} - {meal_type_with_date}{status_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"edit_order:{order[0]}")])
    
    # Добавляем кнопку возврата
    keyboard.append([InlineKeyboardButton(translations.get_button('back'), callback_data="my_orders")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=reply_markup)
    return MENU

@profile_time
async def start_new_order(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает процесс создания нового заказа."""
    try:
        user_id = str(update.effective_user.id)
        
        # Проверяем, авторизован ли пользователь
        if not is_user_authorized(user_id):
            # Если пользователь не авторизован, запрашиваем номер телефона
            keyboard = [[KeyboardButton(translations.get_button('share_phone'), request_contact=True)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
            await update.message.reply_text(translations.get_message('phone_request'), reply_markup=reply_markup)
            return PHONE
            
        # Проверяем время заказа
        if not is_order_time():
            keyboard = [[InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                translations.get_message('wrong_order_time'),
                reply_markup=reply_markup
            )
            return MENU
            
        # Очищаем данные предыдущего заказа
        context.user_data['order'] = {}
        
        # Показываем выбор комнаты
        keyboard = [
            [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(1, 6)],
            [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(6, 11)],
            [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(11, 16)],
            [InlineKeyboardButton(f"{i}", callback_data=f"room:{i}") for i in range(16, 21)],
            [InlineKeyboardButton(translations.get_button('cancel'), callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение с формой заказа
        order_message = await show_order_form(update, context)
        sent_message = await update.message.reply_text(order_message)
        context.user_data['order_chat_id'] = sent_message.chat_id
        context.user_data['order_message_id'] = sent_message.message_id
        
        # Отправляем сообщение с выбором комнаты
        await update.message.reply_text(translations.get_message('choose_room'), reply_markup=reply_markup, parse_mode="MarkdownV2")
        return ROOM
        
    except Exception as e:
        print(f"Ошибка при создании нового заказа: {e}")
        await update.message.reply_text(translations.get_message('error'))
        return MENU 