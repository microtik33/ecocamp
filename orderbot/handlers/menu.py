import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .. import translations
from ..services.user import update_user_info
from ..utils.time_utils import is_order_time, is_menu_available_time
from ..utils.auth_decorator import require_auth
from .order import MENU
from ..services.sheets import (
    get_dishes_for_meal, get_dish_composition, get_today_menu_dishes,
    force_update_menu_cache, force_update_composition_cache, force_update_today_menu_cache,
    is_user_cook
)
from datetime import datetime, timedelta
import logging
import gspread
from .. import config
from telegram.ext import ContextTypes
from ..utils.profiler import profile_time
import asyncio

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
    
    # Отправляем приветственное сообщение
    keyboard = [
        [make_order_button],
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
        
        # Отправляем приветственное сообщение
        keyboard = [
            [make_order_button],
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

@profile_time
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

@profile_time
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

@profile_time
@require_auth
async def show_today_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Показывает меню на сегодня с составами и калорийностью блюд."""
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
                temp_message = await query.edit_message_text(translations.get_message('loading_menu'))
            else:
                temp_message = await update.message.reply_text(translations.get_message('loading_menu'))
        except Exception as e:
            logger.error(f"Ошибка при отправке промежуточного сообщения: {e}")
            if is_callback:
                temp_message = update.callback_query.message
            else:
                temp_message = await update.message.reply_text("...")
        
        try:
            # Получаем блюда из кэша меню на сегодня
            dishes = get_today_menu_dishes()
            
            if not dishes:
                message = "Меню на сегодня не найдено."
                keyboard = [[InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                if is_callback:
                    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)
                else:
                    await temp_message.edit_text(text=message, reply_markup=reply_markup)
                return MENU
            
            # Формируем сообщение с меню
            today_display = datetime.now().strftime("%d.%m")
            message = f"🍽️ Меню на сегодня ({today_display}):\n\n"
            
            # Получаем информацию о составе и калорийности для каждого блюда
            if dishes:
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
            else:
                message += "Нет доступных блюд на сегодня.\n"
            
            # Кнопки навигации
            keyboard = [[InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Отправляем сообщение
            try:
                if is_callback:
                    await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
                else:
                    await temp_message.edit_text(text=message, reply_markup=reply_markup, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Ошибка при отправке меню на сегодня: {e}")
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
        except Exception as e:
            logger.error(f"Ошибка при получении данных из кэша меню на сегодня: {e}")
            message = "Произошла ошибка при получении данных из кэша меню."
            keyboard = [[InlineKeyboardButton(translations.get_button('back_to_menu'), callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if is_callback:
                await update.callback_query.edit_message_text(text=message, reply_markup=reply_markup)
            else:
                await temp_message.edit_text(text=message, reply_markup=reply_markup)
            
        return MENU
    except Exception as e:
        # Глобальная обработка ошибок
        logger.error(f"Критическая ошибка при показе меню на сегодня: {e}")
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

@profile_time
@require_auth
async def update_caches(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """
    Принудительно обновляет все кэши меню.
    
    Эта команда доступна только поварам и обновляет:
    - Кэш меню на завтра
    - Кэш составов блюд
    - Кэш меню на сегодня
    
    Args:
        update: Объект обновления Telegram
        context: Контекст бота с пользовательскими данными
    
    Returns:
        int: Состояние MENU для возврата в главное меню
    """
    user_id = str(update.effective_user.id)
    
    # Проверяем, является ли пользователь поваром
    if not is_user_cook(user_id):
        await update.message.reply_text("⛔ У вас нет прав на выполнение этой команды.")
        return MENU
    
    # Отправляем промежуточное сообщение
    processing_message = await update.message.reply_text("⏳ Обновление кэшей меню...\n\n1. Меню на завтра... ⏳\n2. Составы блюд... ⏳\n3. Меню на сегодня... ⏳")
    
    menu_time = 0
    comp_time = 0
    today_time = 0
    has_error = False
    error_message_text = ""
    
    try:
        # Обновляем кэш меню на завтра
        start_time_menu = datetime.now()
        try:
            await force_update_menu_cache()
            menu_time = (datetime.now() - start_time_menu).total_seconds()
            
            # Обновляем сообщение с прогрессом
            await processing_message.edit_text(
                f"⏳ Обновление кэшей меню...\n\n1. Меню на завтра... ✅ ({menu_time:.1f} сек)\n2. Составы блюд... ⏳\n3. Меню на сегодня... ⏳"
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении кэша меню на завтра: {e}")
            has_error = True
            error_message_text += f"Ошибка при обновлении кэша меню на завтра: {str(e)}\n"
            await processing_message.edit_text(
                f"⏳ Обновление кэшей меню...\n\n1. Меню на завтра... ❌ (ошибка)\n2. Составы блюд... ⏳\n3. Меню на сегодня... ⏳"
            )
        
        # Обновляем кэш составов блюд
        start_time_comp = datetime.now()
        try:
            await force_update_composition_cache()
            comp_time = (datetime.now() - start_time_comp).total_seconds()
            
            # Обновляем сообщение с прогрессом
            status_menu = "✅" if not has_error else "❌"
            await processing_message.edit_text(
                f"⏳ Обновление кэшей меню...\n\n1. Меню на завтра... {status_menu} ({menu_time:.1f} сек)\n2. Составы блюд... ✅ ({comp_time:.1f} сек)\n3. Меню на сегодня... ⏳"
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении кэша составов блюд: {e}")
            has_error = True
            error_message_text += f"Ошибка при обновлении кэша составов блюд: {str(e)}\n"
            status_menu = "✅" if not has_error else "❌"
            await processing_message.edit_text(
                f"⏳ Обновление кэшей меню...\n\n1. Меню на завтра... {status_menu} ({menu_time:.1f} сек)\n2. Составы блюд... ❌ (ошибка)\n3. Меню на сегодня... ⏳"
            )
        
        # Обновляем кэш меню на сегодня
        start_time_today = datetime.now()
        try:
            await force_update_today_menu_cache()
            today_time = (datetime.now() - start_time_today).total_seconds()
            
            status_menu = "✅" if not has_error else "❌"
            status_comp = "✅" if comp_time > 0 else "❌"
            
            if has_error:
                # Если были ошибки, отображаем их
                message = (
                    f"⚠️ Обновление кэшей выполнено с ошибками:\n\n"
                    f"1. Меню на завтра... {status_menu} ({menu_time:.1f} сек)\n"
                    f"2. Составы блюд... {status_comp} ({comp_time:.1f} сек)\n"
                    f"3. Меню на сегодня... ✅ ({today_time:.1f} сек)\n\n"
                    f"⚠️ Ошибки при обновлении:\n{error_message_text}\n"
                    f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                await processing_message.edit_text(message)
            else:
                # Формируем сообщение об успешном обновлении
                total_time = menu_time + comp_time + today_time
                success_message = (
                    "✅ Кэши успешно обновлены:\n\n"
                    f"1. Меню на завтра... ✅ ({menu_time:.1f} сек)\n"
                    f"2. Составы блюд... ✅ ({comp_time:.1f} сек)\n"
                    f"3. Меню на сегодня... ✅ ({today_time:.1f} сек)\n\n"
                    f"⏱ Общее время: {total_time:.1f} сек\n"
                    f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                await processing_message.edit_text(success_message)
        except Exception as e:
            logger.error(f"Ошибка при обновлении кэша меню на сегодня: {e}")
            has_error = True
            error_message_text += f"Ошибка при обновлении кэша меню на сегодня: {str(e)}\n"
            
            status_menu = "✅" if not has_error else "❌"
            status_comp = "✅" if comp_time > 0 else "❌"
            
            message = (
                f"⚠️ Обновление кэшей выполнено с ошибками:\n\n"
                f"1. Меню на завтра... {status_menu} ({menu_time:.1f} сек)\n"
                f"2. Составы блюд... {status_comp} ({comp_time:.1f} сек)\n"
                f"3. Меню на сегодня... ❌ (ошибка)\n\n"
                f"⚠️ Ошибки при обновлении:\n{error_message_text}\n"
                f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            )
            await processing_message.edit_text(message)
    except Exception as e:
        # Логируем ошибку
        logger.error(f"Ошибка при обновлении кэшей: {e}")
        
        # Формируем сообщение об ошибке
        error_message = (
            "❌ Произошла ошибка при обновлении кэшей.\n"
            f"Ошибка: {str(e)}"
        )
        
        # Обновляем промежуточное сообщение
        await processing_message.edit_text(error_message)
    
    return MENU 

async def force_update_menu_cache():
    """
    Принудительно обновляет кэш меню на завтра.
    
    Returns:
        bool: True в случае успешного обновления
    """
    # Обновляем кэш меню (очищаем его, чтобы заставить загрузить новые данные)
    get_dishes_for_meal.cache_clear()
    
    # Запрашиваем все блюда для каждого приема пищи, чтобы заполнить кэш
    # Это заставит функцию get_dishes_for_meal загрузить новые данные
    breakfast_dishes = get_dishes_for_meal('breakfast')
    lunch_dishes = get_dishes_for_meal('lunch')
    dinner_dishes = get_dishes_for_meal('dinner')
    
    # Проверяем, что данные загружены
    if breakfast_dishes or lunch_dishes or dinner_dishes:
        logger.info(f"Кэш меню обновлен: завтрак ({len(breakfast_dishes)} блюд), "
                   f"обед ({len(lunch_dishes)} блюд), "
                   f"ужин ({len(dinner_dishes)} блюд)")
        return True
    else:
        logger.warning("Не удалось обновить кэш меню. Данные не загружены.")
        return False 