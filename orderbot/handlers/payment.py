import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
import logging
import asyncio
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import io
import base64
from PIL import Image

from ..services import sbp
from .. import translations
from ..services.sheets import get_orders_sheet, update_order
from ..config import TOCHKA_ACCOUNT_ID, TOCHKA_MERCHANT_ID, TOCHKA_JWT_TOKEN
from ..utils.auth_decorator import require_auth
from .states import MENU, PAYMENT

# Настройка логгера
logger = logging.getLogger(__name__)

# Время ожидания оплаты (в секундах) для проверки статуса
PAYMENT_CHECK_INTERVAL = 10
PAYMENT_MAX_CHECKS = 12  # 2 минуты максимум (12 * 10 секунд)

@require_auth
async def create_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Создает QR-код для оплаты через СБП
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
        
    Returns:
        int: Следующее состояние беседы
    """
    query = update.callback_query
    await query.answer()
    
    # Проверяем, настроены ли переменные окружения для API Точка банка
    if not TOCHKA_JWT_TOKEN or not TOCHKA_ACCOUNT_ID or not TOCHKA_MERCHANT_ID:
        logging.error("Отсутствуют необходимые переменные окружения для API Точка Банка")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Оплата через СБП временно недоступна. Пожалуйста, обратитесь к администратору.",
            reply_markup=reply_markup
        )
        return MENU
    
    # Отправляем промежуточное сообщение
    await query.edit_message_text(translations.get_message('payment_processing'))
    
    # Получаем сумму всех активных заказов пользователя
    user_id = str(update.effective_user.id)
    
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Принят', 'Активен']]
    
    if not user_orders:
        keyboard = [
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')],
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            translations.get_message('no_active_orders'),
            reply_markup=reply_markup
        )
        return MENU
    
    # Рассчитываем общую сумму заказов
    total_sum = sum(int(float(order[5])) for order in user_orders if order[5])
    
    if total_sum <= 0:
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Сумма к оплате должна быть больше 0",
            reply_markup=reply_markup
        )
        return MENU
    
    # Конвертируем сумму в копейки для API
    amount_kopecks = int(total_sum * 100)
    
    # Формируем назначение платежа
    payment_purpose = f"Оплата заказов в EcoCamp (пользователь {user_id})"
    
    try:
        # Создаем QR-код
        qr_data = sbp.register_qr_code(
            account_id=TOCHKA_ACCOUNT_ID,
            merchant_id=TOCHKA_MERCHANT_ID,
            amount=amount_kopecks,
            payment_purpose=payment_purpose
        )
        
        if not qr_data or 'qrcId' not in qr_data:
            # Ошибка при создании QR-кода
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_error'),
                reply_markup=reply_markup
            )
            return MENU
        
        # Сохраняем данные о платеже в контексте
        context.user_data['payment'] = {
            'qrc_id': qr_data['qrcId'],
            'amount': total_sum,
            'orders': [order[0] for order in user_orders],  # Список ID заказов
            'created_at': datetime.now().isoformat(),
            'payload': qr_data.get('payload', '')
        }
        
        # Декодируем изображение QR-кода из base64
        qr_image_data = qr_data.get('image', '')
        if qr_image_data:
            try:
                # Удаляем префикс data:image/png;base64, если он есть
                if ',' in qr_image_data:
                    qr_image_data = qr_image_data.split(',', 1)[1]
                
                # Декодируем base64 в бинарные данные
                image_bytes = base64.b64decode(qr_image_data)
                image = Image.open(io.BytesIO(image_bytes))
                
                # Сохраняем изображение во временный файл
                buffer = io.BytesIO()
                image.save(buffer, format='PNG')
                buffer.seek(0)
                
                # Формируем сообщение с QR-кодом
                message_text = (
                    f"{translations.get_message('payment_qr_created')}\n\n"
                    f"Сумма к оплате: {total_sum} руб.\n\n"
                    f"{translations.get_message('payment_instructions')}"
                )
                
                # Добавляем клавиатуру
                keyboard = [
                    [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                    [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Отправляем новое сообщение с изображением
                await query.delete_message()
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=buffer,
                    caption=message_text,
                    reply_markup=reply_markup
                )
                
                # Если есть ссылка на оплату, отправляем ее отдельным сообщением
                if context.user_data['payment'].get('payload'):
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=f"Ссылка для оплаты: {context.user_data['payment']['payload']}"
                    )
                
                return PAYMENT
                
            except Exception as e:
                logger.error(f"Ошибка при обработке изображения QR-кода: {e}")
                
                # Отправляем сообщение только с текстом и ссылкой
                message_text = (
                    f"{translations.get_message('payment_qr_created')}\n\n"
                    f"Сумма к оплате: {total_sum} руб.\n\n"
                )
                
                if context.user_data['payment'].get('payload'):
                    message_text += f"\nСсылка для оплаты: {context.user_data['payment']['payload']}\n\n"
                
                message_text += translations.get_message('payment_instructions')
                
                # Добавляем клавиатуру
                keyboard = [
                    [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                    [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(message_text, reply_markup=reply_markup)
                return PAYMENT
        
        # Если изображения нет, отправляем только текст со ссылкой
        message_text = (
            f"{translations.get_message('payment_qr_created')}\n\n"
            f"Сумма к оплате: {total_sum} руб.\n\n"
        )
        
        if context.user_data['payment'].get('payload'):
            message_text += f"\nСсылка для оплаты: {context.user_data['payment']['payload']}\n\n"
        
        message_text += translations.get_message('payment_instructions')
        
        # Добавляем клавиатуру
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message_text, reply_markup=reply_markup)
        return PAYMENT
        
    except Exception as e:
        logger.error(f"Ошибка при создании QR-кода: {e}")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            translations.get_message('payment_error'),
            reply_markup=reply_markup
        )
        return MENU

@require_auth
async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Проверяет статус оплаты
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
        
    Returns:
        int: Следующее состояние беседы
    """
    query = update.callback_query
    await query.answer()
    
    # Проверяем, есть ли данные о платеже
    if 'payment' not in context.user_data or 'qrc_id' not in context.user_data['payment']:
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Данные о платеже не найдены. Попробуйте создать новый платеж.",
            reply_markup=reply_markup
        )
        return MENU
    
    # Отправляем сообщение о проверке статуса
    await query.edit_message_text(translations.get_message('payment_status_check'))
    
    try:
        # Проверяем статус оплаты
        qrc_id = context.user_data['payment']['qrc_id']
        status_data = sbp.get_qr_code_status(qrc_id)
        
        if not status_data:
            # Ошибка при получении статуса
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Не удалось получить статус оплаты. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
            return PAYMENT
        
        # Проверяем статус платежа
        payment_status = status_data.get('status', '').lower()
        
        if payment_status == 'paid':
            # Оплата успешна
            # Обновляем статусы заказов
            orders_sheet = get_orders_sheet()
            all_orders = orders_sheet.get_all_values()
            
            for order_id in context.user_data['payment']['orders']:
                for idx, row in enumerate(all_orders):
                    if row[0] == order_id and row[2] in ['Принят', 'Активен']:
                        # Обновляем статус заказа на "Оплачен"
                        orders_sheet.update_cell(idx + 1, 3, 'Оплачен')
            
            # Отправляем сообщение об успешной оплате
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_success'),
                reply_markup=reply_markup
            )
            
            # Очищаем данные о платеже
            if 'payment' in context.user_data:
                del context.user_data['payment']
            
            return MENU
            
        elif payment_status == 'expired':
            # Время действия QR-кода истекло
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_expired'),
                reply_markup=reply_markup
            )
            
            # Очищаем данные о платеже
            if 'payment' in context.user_data:
                del context.user_data['payment']
            
            return MENU
            
        else:
            # Платеж в процессе или другой статус
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_waiting'),
                reply_markup=reply_markup
            )
            return PAYMENT
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса оплаты: {e}")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Произошла ошибка при проверке статуса оплаты. Попробуйте еще раз.",
            reply_markup=reply_markup
        )
        return PAYMENT

@require_auth
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменяет текущий платеж
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
        
    Returns:
        int: Следующее состояние беседы
    """
    query = update.callback_query
    await query.answer()
    
    # Очищаем данные о платеже
    if 'payment' in context.user_data:
        del context.user_data['payment']
    
    # Отправляем сообщение об отмене
    keyboard = [
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
        [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        translations.get_message('payment_cancel'),
        reply_markup=reply_markup
    )
    return MENU 