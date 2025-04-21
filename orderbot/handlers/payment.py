"""
Обработчики платежей через СБП (Точка банк)
"""
import asyncio
import logging
import io
import base64
import qrcode
from typing import Dict, Any, Optional, List, Tuple

import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import ContextTypes

from orderbot import translations
from orderbot.handlers.states import MENU
from orderbot.handlers.auth import require_auth
from orderbot.utils.helpers import escape_markdown_v2, profile_time
from orderbot.services.payment import tochka_client

logger = logging.getLogger(__name__)

# Константы для кэширования QR-кодов
PAYMENT_CACHE: Dict[str, Dict[str, Any]] = {}


async def generate_qr_code_image(qr_url: str) -> io.BytesIO:
    """
    Генерирует изображение QR-кода из URL.

    Args:
        qr_url: URL для QR-кода

    Returns:
        io.BytesIO: Изображение QR-кода в виде байтового потока
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


@profile_time
@require_auth
async def pay_with_sbp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Создает платеж через СБП для оплаты заказов пользователя.

    Args:
        update: Объект обновления от Telegram
        context: Контекст бота

    Returns:
        int: Следующее состояние бота
    """
    # Определяем, как была вызвана функция - через команду или через кнопку
    is_command = bool(update.message)
    
    if not is_command:
        query = update.callback_query
        await query.answer()
    
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    # Инициализируем состояние MENU, если оно не установлено
    if 'state' not in context.user_data:
        context.user_data['state'] = MENU
    
    # Получаем заказы пользователя
    from orderbot.services.sheets import get_orders_sheet
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    # Фильтруем заказы пользователя со статусами "Принят" и "Активен"
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Принят', 'Активен']]
    
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
        
        return MENU
    
    # Рассчитываем общую сумму заказов
    total_sum = sum(int(float(order[5])) if order[5] else 0 for order in user_orders)
    
    # Если нет заказов или сумма равна 0, то нечего оплачивать
    if total_sum <= 0:
        message = escape_markdown_v2("У вас нет неоплаченных заказов или сумма заказов равна 0.")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if is_command:
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.callback_query.edit_message_text(message, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        
        return MENU
    
    # Формируем описание платежа
    order_ids = ", ".join([order[0] for order in user_orders])
    payment_description = f"Оплата заказов {order_ids} в ЭкоКемп"
    
    try:
        # Создаем QR-код для оплаты через СБП
        qr_result = await tochka_client.create_qr_code(
            amount=total_sum,
            order_id=f"orders_{user_id}_{order_ids.replace(', ', '_')}",
            description=payment_description
        )
        
        if not qr_result or "qrcId" not in qr_result:
            raise Exception("API Точка банка не вернуло идентификатор QR-кода")
        
        qrc_id = qr_result.get("qrcId")
        qrc_url = qr_result.get("payload")
        
        if not qrc_url:
            raise Exception("API Точка банка не вернуло URL для QR-кода")
        
        # Кэшируем информацию о платеже
        PAYMENT_CACHE[user_id] = {
            "qrc_id": qrc_id,
            "qrc_url": qrc_url,
            "amount": total_sum,
            "order_ids": order_ids,
            "status": "PENDING"
        }
        
        # Генерируем QR-код как изображение
        qr_image = await generate_qr_code_image(qrc_url)
        
        # Отправляем сообщение с QR-кодом и информацией о платеже
        message_text = (
            f"{translations.get_message('pay_with_sbp')}\n\n"
            f"Сумма к оплате: {total_sum} руб.\n"
            f"Заказы: {order_ids}\n\n"
            f"{translations.get_message('pay_with_sbp_info')}"
        )
        
        # Кнопки для взаимодействия с оплатой
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('open_qr_code'), callback_data='open_qr_code')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем QR-код и сообщение
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=qr_image,
            caption=message_text,
            reply_markup=reply_markup
        )
        
        # Уведомляем пользователя в исходном сообщении
        success_message = translations.get_message('sbp_payment_created', amount=str(total_sum))
        if is_command:
            if update.message:
                await update.message.reply_text(success_message)
        else:
            if update.callback_query:
                await update.callback_query.edit_message_text(success_message)
        
        logger.info(f"Создан QR-код для оплаты пользователем {user_id} на сумму {total_sum} руб.")
    
    except Exception as e:
        logger.error(f"Ошибка при создании QR-кода: {e}")
        error_message = translations.get_message('sbp_payment_error', error=str(e))
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
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
async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Проверяет статус платежа через СБП.

    Args:
        update: Объект обновления от Telegram
        context: Контекст бота

    Returns:
        int: Следующее состояние бота
    """
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Проверяем, есть ли информация о платеже в кэше
    if user_id not in PAYMENT_CACHE:
        message = translations.get_message('sbp_payment_expired')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('pay_sbp'), callback_data='pay_sbp')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_caption(
            caption=message,
            reply_markup=reply_markup
        )
        return MENU
    
    payment_info = PAYMENT_CACHE[user_id]
    qrc_id = payment_info.get("qrc_id")
    
    try:
        # Получаем статус платежа из API Точка банка
        payment_status = await tochka_client.get_payment_status(qrc_id)
        status = payment_status.get("status", "NotFound")
        
        # Обновляем статус в кэше
        payment_info["status"] = status
        PAYMENT_CACHE[user_id] = payment_info
        
        # Обрабатываем разные статусы платежа
        if status == "Confirming" or status == "ACWP":
            # Платеж успешно выполнен
            message = translations.get_message('sbp_payment_success', amount=str(payment_info.get("amount", 0)))
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_caption(
                caption=message,
                reply_markup=reply_markup
            )
            
            # Удаляем информацию о платеже из кэша после успешной оплаты
            if user_id in PAYMENT_CACHE:
                del PAYMENT_CACHE[user_id]
        
        elif status == "NotFound":
            # Платеж не найден
            message = translations.get_message('sbp_payment_expired')
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_sbp'), callback_data='pay_sbp')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_caption(
                caption=message,
                reply_markup=reply_markup
            )
            
            # Удаляем информацию о платеже из кэша
            if user_id in PAYMENT_CACHE:
                del PAYMENT_CACHE[user_id]
        
        else:
            # Платеж в другом статусе (обрабатывается, ожидает и т.д.)
            message = (
                f"{translations.get_message('sbp_payment_pending')}\n\n"
                f"Статус платежа: {status}\n"
                f"Сумма к оплате: {payment_info.get('amount', 0)} руб.\n"
                f"Заказы: {payment_info.get('order_ids', '')}\n\n"
                f"{translations.get_message('pay_with_sbp_info')}"
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('open_qr_code'), callback_data='open_qr_code')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_caption(
                caption=message,
                reply_markup=reply_markup
            )
    
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса платежа: {e}")
        message = f"Ошибка при проверке статуса платежа: {e}"
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_caption(
            caption=message,
            reply_markup=reply_markup
        )
    
    return MENU


@profile_time
@require_auth
async def open_qr_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Открывает QR-код в полном размере для оплаты.

    Args:
        update: Объект обновления от Telegram
        context: Контекст бота

    Returns:
        int: Следующее состояние бота
    """
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    # Проверяем, есть ли информация о платеже в кэше
    if user_id not in PAYMENT_CACHE:
        message = translations.get_message('sbp_payment_expired')
        keyboard = [
            [InlineKeyboardButton(translations.get_button('pay_sbp'), callback_data='pay_sbp')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_caption(
            caption=message,
            reply_markup=reply_markup
        )
        return MENU
    
    payment_info = PAYMENT_CACHE[user_id]
    qrc_url = payment_info.get("qrc_url")
    
    if not qrc_url:
        message = "QR-код не найден или срок его действия истек."
        keyboard = [
            [InlineKeyboardButton(translations.get_button('pay_sbp'), callback_data='pay_sbp')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_caption(
            caption=message,
            reply_markup=reply_markup
        )
        return MENU
    
    try:
        # Генерируем QR-код как изображение в большом размере
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=20,  # Увеличенный размер для лучшей видимости
            border=4,
        )
        qr.add_data(qrc_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        img.save(bio, "PNG")
        bio.seek(0)
        
        # Отправляем большой QR-код отдельным сообщением
        message = f"QR-код для оплаты {payment_info.get('amount', 0)} руб."
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=bio,
            caption=message
        )
    
    except Exception as e:
        logger.error(f"Ошибка при открытии QR-кода: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Ошибка при открытии QR-кода: {e}"
        )
    
    return MENU


@profile_time
@require_auth
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет процесс оплаты через СБП.

    Args:
        update: Объект обновления от Telegram
        context: Контекст бота

    Returns:
        int: Следующее состояние бота
    """
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    # Удаляем информацию о платеже из кэша
    if user_id in PAYMENT_CACHE:
        del PAYMENT_CACHE[user_id]
    
    message = translations.get_message('sbp_payment_cancelled')
    keyboard = [
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_caption(
        caption=message,
        reply_markup=reply_markup
    )
    
    return MENU 