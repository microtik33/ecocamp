import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .. import translations
from ..services.user import update_user_info
from ..utils.time_utils import is_order_time, is_menu_available_time
from ..utils.auth_decorator import require_auth
from .order import MENU
from ..services.sheets import get_dishes_for_meal, get_dish_composition
from datetime import datetime, timedelta
import logging

# Настройка логгера
logger = logging.getLogger(__name__)

@require_auth
async def start(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом."""
    context.user_data.clear()
    
    # Обновляем информацию о пользователе
    user = update.effective_user
    await update_user_info(user)
    
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
    can_show_menu = is_menu_available_time()
    menu_button = InlineKeyboardButton(
        translations.get_button('tomorrow_menu'), 
        callback_data='tomorrow_menu'
    )
    
    today_menu_button = InlineKeyboardButton(
        translations.get_button('today_menu'), 
        callback_data='today_menu'
    )
    
    # Отправляем приветственное сообщение
    keyboard = [
        [make_order_button],
        [today_menu_button],
        [menu_button],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Проверяем, вызвана ли функция из обработчика сообщения или из callback
    if update.message:
        await update.message.reply_text(translations.get_message('welcome'), reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text=translations.get_message('welcome'), 
            reply_markup=reply_markup
        )
    
    return MENU 

@require_auth
async def back_to_main_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Обработчик для возврата в главное меню из любой точки."""
    try:
        # Убедимся, что контекст разговора инициализирован корректно
        if 'conversation_state' not in context.user_data:
            context.user_data['conversation_state'] = MENU
        
        query = update.callback_query
        await query.answer()
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
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
        can_show_menu = is_menu_available_time()
        menu_button = InlineKeyboardButton(
            translations.get_button('tomorrow_menu'), 
            callback_data='tomorrow_menu'
        )
        
        today_menu_button = InlineKeyboardButton(
            translations.get_button('today_menu'), 
            callback_data='today_menu'
        )
        
        # Отправляем приветственное сообщение
        keyboard = [
            [make_order_button],
            [today_menu_button],
            [menu_button],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('ask_question'), callback_data='question')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text=translations.get_message('welcome'), 
            reply_markup=reply_markup
        )
        
        return MENU
    except Exception as e:
        # Глобальная обработка ошибок
        logger.error(f"Критическая ошибка при возврате в главное меню: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке
            error_message = translations.get_message('error_loading_menu')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=error_message, 
                    reply_markup=reply_markup
                )
            elif update.message:
                await update.message.reply_text(
                    text=error_message,
                    reply_markup=reply_markup
                )
        except:
            # Если даже отправка сообщения об ошибке не удалась, просто игнорируем
            pass
        return MENU

@require_auth
async def show_tomorrow_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показывает меню на завтра."""
    try:
        # Убедимся, что контекст разговора инициализирован корректно
        # Это обеспечит работу кнопок даже если пользователь начал с /menu
        if 'conversation_state' not in context.user_data:
            context.user_data['conversation_state'] = MENU
        
        # Определяем источник вызова (команда или callback)
        is_callback = update.callback_query is not None
        
        # Отправляем промежуточное сообщение
        try:
            if is_callback:
                query = update.callback_query
                await query.answer()
                # В случае callback не можем отправить новое сообщение, но можем изменить текущее
                temp_message = await query.edit_message_text(translations.get_message('loading_menu'))
            else:
                # Для команды можем отправить новое сообщение
                temp_message = await update.message.reply_text(translations.get_message('loading_menu'))
        except Exception as e:
            # В случае ошибки при отправке промежуточного сообщения, логируем и продолжаем
            logger.error(f"Ошибка при отправке промежуточного сообщения: {e}")
            # Создаем фиктивный объект сообщения для совместимости
            if is_callback:
                temp_message = update.callback_query.message
            else:
                # Если не удалось отправить промежуточное сообщение, отправляем новое
                temp_message = await update.message.reply_text("...")
        
        # Проверяем, доступно ли меню в текущее время
        if not is_menu_available_time():
            # Если меню недоступно, отображаем сообщение и кнопку возврата
            message = translations.get_message('menu_not_available')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                if is_callback:
                    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)
                else:
                    await temp_message.edit_text(text=message, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при отображении сообщения о недоступности меню: {e}")
            return MENU
        
        # Получаем завтрашнюю дату
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m")
        
        # Формируем сообщение с меню
        message = f"🍽️ Меню на {tomorrow}:\n\n"
        
        # Добавляем блюда для завтрака
        message += "🌅 *Завтрак*\n"
        breakfast_dishes = get_dishes_for_meal('breakfast')
        if breakfast_dishes:
            for dish, price, weight in breakfast_dishes:
                if dish.strip():  # Проверяем, что название блюда не пустое
                    message += f"- *{dish}* ({weight}) {price} р\n"
        else:
            message += "Нет доступных блюд\n"
        
        message += "\n🕛 *Обед*\n"
        lunch_dishes = get_dishes_for_meal('lunch')
        if lunch_dishes:
            for dish, price, weight in lunch_dishes:
                if dish.strip():  # Проверяем, что название блюда не пустое
                    message += f"- *{dish}* ({weight}) {price} р\n"
        else:
            message += "Нет доступных блюд\n"
        
        message += "\n🌇 *Ужин*\n"
        dinner_dishes = get_dishes_for_meal('dinner')
        if dinner_dishes:
            for dish, price, weight in dinner_dishes:
                if dish.strip():  # Проверяем, что название блюда не пустое
                    message += f"- *{dish}* ({weight}) {price} р\n"
        else:
            message += "Нет доступных блюд\n"
        
        # Кнопки возврата в главное меню и просмотра составов
        keyboard = [
            [InlineKeyboardButton(translations.get_button('dish_compositions'), callback_data='show_compositions')],
            [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем или редактируем сообщение в зависимости от источника вызова
        try:
            if is_callback:
                await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await temp_message.edit_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка при отправке меню: {e}")
            # Пытаемся отправить сообщение повторно
            try:
                if is_callback:
                    await update.callback_query.edit_message_text(
                        text=translations.get_message('error_loading_menu'), 
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')
                        ]])
                    )
                else:
                    await update.message.reply_text(
                        text=translations.get_message('error_loading_menu'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')
                        ]])
                    )
            except:
                pass
            
        return MENU
    except Exception as e:
        # Глобальная обработка ошибок
        logger.error(f"Критическая ошибка при показе меню: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке
            error_message = translations.get_message('error_loading_menu')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=error_message, 
                    reply_markup=reply_markup
                )
            elif update.message:
                await update.message.reply_text(
                    text=error_message,
                    reply_markup=reply_markup
                )
        except:
            # Если даже отправка сообщения об ошибке не удалась, просто игнорируем
            pass
        return MENU

@require_auth
async def show_dish_compositions(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показывает составы блюд из меню."""
    try:
        # Убедимся, что контекст разговора инициализирован корректно
        if 'conversation_state' not in context.user_data:
            context.user_data['conversation_state'] = MENU
        
        query = update.callback_query
        await query.answer()
        
        # Отправляем промежуточное сообщение
        try:
            await query.edit_message_text(translations.get_message('loading_compositions'))
        except Exception as e:
            # В случае ошибки редактирования просто логируем и продолжаем
            logger.error(f"Ошибка при отправке промежуточного сообщения: {e}")
        
        # Проверяем, доступно ли меню в текущее время
        if not is_menu_available_time():
            # Если меню недоступно, отображаем сообщение и кнопку возврата
            message = translations.get_message('menu_not_available')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text=message, reply_markup=reply_markup)
            return MENU
        
        # Получаем завтрашнюю дату
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d.%m")
        
        # Формируем сообщение с составами
        message = f"🍴 Составы блюд на {tomorrow}:\n\n"
        
        # Функция для добавления информации о составах блюд
        def add_compositions_for_meal_type(meal_type, meal_title):
            nonlocal message
            message += f"*{meal_title}:*\n\n"
            dishes = get_dishes_for_meal(meal_type)
            if dishes:
                for dish, _, _ in dishes:
                    if dish.strip():  # Проверяем, что название блюда не пустое
                        composition_info = get_dish_composition(dish)
                        message += f"*{dish}*\n"
                        if composition_info['composition']:
                            message += f"{composition_info['composition']}\n"
                        else:
                            message += "Состав не указан\n"
                        if composition_info['calories']:
                            message += f"_{composition_info['calories']} ккал_\n"
                        message += "\n"
            else:
                message += "Нет доступных блюд\n\n"
        
        # Добавляем составы для каждого типа приема пищи
        add_compositions_for_meal_type('breakfast', 'Завтрак')
        add_compositions_for_meal_type('lunch', 'Обед')
        add_compositions_for_meal_type('dinner', 'Ужин')
        
        # Кнопки навигации
        keyboard = [
            [InlineKeyboardButton(translations.get_button('back_to_menu_list'), callback_data='tomorrow_menu')],
            [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
        return MENU
    except Exception as e:
        # Глобальная обработка ошибок, чтобы функция не падала полностью
        logger.error(f"Ошибка при показе составов блюд: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке
            error_message = translations.get_message('error_loading_compositions')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=error_message, 
                    reply_markup=reply_markup
                )
        except:
            # Если даже отправка сообщения об ошибке не удалась, просто игнорируем
            pass
        return MENU 

@require_auth
async def show_today_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показывает меню на сегодня с составами блюд."""
    try:
        # Убедимся, что контекст разговора инициализирован корректно
        if 'conversation_state' not in context.user_data:
            context.user_data['conversation_state'] = MENU
        
        # Определяем источник вызова (команда или callback)
        is_callback = update.callback_query is not None
        
        # Отправляем промежуточное сообщение
        try:
            if is_callback:
                query = update.callback_query
                await query.answer()
                temp_message = await query.edit_message_text(translations.get_message('loading_compositions'))
            else:
                temp_message = await update.message.reply_text(translations.get_message('loading_compositions'))
        except Exception as e:
            logger.error(f"Ошибка при отправке промежуточного сообщения: {e}")
            if is_callback:
                temp_message = update.callback_query.message
            else:
                temp_message = await update.message.reply_text("...")
        
        # Получаем сегодняшнюю дату в формате дд.мм.гг
        today = datetime.now().strftime("%d.%m.%y")
        
        # Импортируем необходимые константы и функции
        from ..services.sheets import client, get_composition_sheet, get_dish_composition
        
        # Получаем лист с меню на сегодня
        sheet = client.open_by_key("1169304186").sheet1
        
        # Ищем строку с сегодняшней датой
        all_values = sheet.get_all_values()
        
        found_row = None
        for row in all_values:
            if row[0] == today:
                found_row = row
                break
                
        if not found_row:
            # Если данных на сегодня нет
            message = f"На сегодня ({today}) меню не найдено."
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                if is_callback:
                    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)
                else:
                    await temp_message.edit_text(text=message, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при отображении сообщения о ненайденном меню: {e}")
            return MENU
        
        # Формируем сообщение с составами блюд на сегодня
        message = f"🍴 Меню на сегодня ({today}):\n\n"
        
        # Получаем список блюд из найденной строки (колонки 3-41)
        # Индексы в Python начинаются с 0, поэтому колонки 3-41 это индексы 2-40
        dishes = [dish.strip() for dish in found_row[2:41] if dish.strip()]
                
        # Добавляем информацию о блюдах
        for dish in dishes:
            composition_info = get_dish_composition(dish)
            message += f"*{dish}*\n"
            if composition_info['composition']:
                message += f"{composition_info['composition']}\n"
            else:
                message += "Состав не указан\n"
            if composition_info['calories']:
                message += f"_{composition_info['calories']} ккал_\n"
            message += "\n"
            
        # Если блюд не найдено
        if not dishes:
            message += "Блюда на сегодня не найдены.\n"
            
        # Кнопки навигации
        keyboard = [
            [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение
        try:
            if is_callback:
                await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await temp_message.edit_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Ошибка при отправке меню на сегодня: {e}")
            # Пытаемся отправить сообщение повторно
            try:
                if is_callback:
                    await update.callback_query.edit_message_text(
                        text=translations.get_message('error_loading_compositions'), 
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')
                        ]])
                    )
                else:
                    await update.message.reply_text(
                        text=translations.get_message('error_loading_compositions'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')
                        ]])
                    )
            except:
                pass
                
        return MENU
    except Exception as e:
        # Глобальная обработка ошибок
        logger.error(f"Критическая ошибка при показе меню на сегодня: {e}")
        try:
            # Пытаемся отправить сообщение об ошибке
            error_message = translations.get_message('error_loading_compositions')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=error_message, 
                    reply_markup=reply_markup
                )
            elif update.message:
                await update.message.reply_text(
                    text=error_message,
                    reply_markup=reply_markup
                )
        except:
            # Если даже отправка сообщения об ошибке не удалась, просто игнорируем
            pass
        return MENU 