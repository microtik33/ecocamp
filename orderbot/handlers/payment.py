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
from ..services.sheets import get_orders_sheet, update_order, save_payment_info, get_payments_sheet
from ..config import TOCHKA_ACCOUNT_ID, TOCHKA_MERCHANT_ID, TOCHKA_JWT_TOKEN
from ..utils.auth_decorator import require_auth
from .states import MENU, PAYMENT
from ..services.payment_storage import store_payment, update_payment_message_ids, get_payment, remove_payment

# Настройка логгера
logger = logging.getLogger(__name__)

# Максимальное число попыток проверки статуса
MAX_STATUS_CHECKS = 20
# Интервал между проверками в секундах
STATUS_CHECK_INTERVAL = 15

@require_auth
async def create_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Создает новый платеж
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
        
    Returns:
        int: Следующее состояние беседы
    """
    query = update.callback_query
    await query.answer()
    
    # Получаем активные заказы пользователя
    orders_sheet = get_orders_sheet()
    all_orders = orders_sheet.get_all_values()
    user_orders = [order for order in all_orders if order[1] == str(update.effective_user.id) and order[2] in ['Принят', 'Активен', 'Ожидает оплаты']]
    
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
    payment_purpose = f"Оплата заказа"
    
    try:
        # Создаем QR-код для оплаты
        qr_data = sbp.create_qr_code(
            amount=amount_kopecks,
            purpose=payment_purpose,
            account_id=TOCHKA_ACCOUNT_ID,
            merchant_id=TOCHKA_MERCHANT_ID,
            jwt_token=TOCHKA_JWT_TOKEN
        )
        
        if not qr_data:
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_error'),
                reply_markup=reply_markup
            )
            return MENU
        
        # Сохраняем информацию о платеже
        payment_id = await save_payment_info(
            user_id=update.effective_user.id,
            amount=total_sum,
            qrc_id=qr_data.get('qrc_id', ''),
            status='создан'
        )
        
        # Сохраняем данные платежа в хранилище
        payment_data = {
            'payment_id': payment_id,
            'qrc_id': qr_data.get('qrc_id', ''),
            'amount': total_sum,
            'orders': [order[0] for order in user_orders],
            'status_checks': 0
        }
        store_payment(update.effective_chat.id, payment_data)
        
        # Формируем сообщение с информацией о платеже
        message_text = (
            f"{translations.get_message('payment_qr_created')}\n\n"
            f"Сумма к оплате: *{total_sum} руб.*\n\n"
        )
        
        # Добавляем ссылку на оплату, если она есть
        payment_url = qr_data.get('payload', '')
        if payment_url:
            message_text += f"Также можете оплатить по ссылке: {payment_url}\n\n"
        
        message_text += translations.get_message('payment_instructions')
        
        # Удаляем старое сообщение
        await query.delete_message()
        
        # 1. Отправляем сообщение с QR-кодом и информацией о платеже
        qr_message = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=qr_data.get('image', ''),
            caption=message_text,
            parse_mode='Markdown'
        )
        
        # 2. Отправляем отдельное сообщение с кнопками управления платежом
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        buttons_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Если оплата не подтвердилась автоматически, нажмите на кнопку 'Проверить статус оплаты':",
            reply_markup=reply_markup
        )
        
        # Сохраняем ID сообщений в хранилище
        update_payment_message_ids(
            chat_id=update.effective_chat.id,
            qr_message_id=qr_message.message_id,
            buttons_message_id=buttons_message.message_id
        )
        
        # Запускаем автоматическую проверку статуса платежа
        try:
            auto_check_success = start_auto_check_payment(context, update.effective_chat.id, payment_data)
            if not auto_check_success:
                logger.info(f"Не удалось запустить автоматическую проверку платежа при создании")
        except Exception as e:
            logger.error(f"Ошибка при запуске автоматической проверки платежа: {e}")
        
        return PAYMENT
        
    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            translations.get_message('payment_error'),
            reply_markup=reply_markup
        )
        return MENU

# Функция для автоматической проверки статуса платежа
async def auto_check_payment_status(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Автоматически проверяет статус оплаты с заданным интервалом
    
    Args:
        context: Контекст бота
    """
    job = context.job
    chat_id = job.data['chat_id']
    
    # Получаем данные платежа из хранилища
    payment_data = get_payment(chat_id)
    
    try:
        # Проверяем, есть ли данные о платеже
        if not payment_data or 'qrc_id' not in payment_data:
            # Платеж не найден, отменяем задачу
            logger.info(f"Автопроверка: данные о платеже не найдены")
            return
        
        # Увеличиваем счетчик проверок
        payment_data['status_checks'] += 1
        
        # Проверяем наличие ID сообщения с кнопками
        if 'buttons_message_id' not in payment_data:
            logger.warning(f"Автопроверка: не найден ID сообщения с кнопками")
            return
            
        buttons_message_id = payment_data['buttons_message_id']
        
        # Проверяем, не превышено ли максимальное число попыток
        if payment_data['status_checks'] > MAX_STATUS_CHECKS:
            logger.info(f"Автопроверка: достигнуто максимальное число попыток ({MAX_STATUS_CHECKS})")
            
            # Отправляем сообщение о превышении числа попыток
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=buttons_message_id,
                text="Автоматическая проверка завершена. Нажмите кнопку для ручной проверки статуса.",
                reply_markup=reply_markup
            )
            
            # Отменяем задачу
            return
        
        # Проверяем статус оплаты
        qrc_id = payment_data['qrc_id']
        logger.info(f"Автопроверка: запрос статуса QR-кода {qrc_id}, попытка {payment_data['status_checks']}")
        
        status_data = sbp.get_qr_code_status(qrc_id)
        
        if not status_data:
            logger.warning(f"Автопроверка: не удалось получить статус оплаты")
            return
        
        # Проверяем статус платежа
        payment_status = status_data.get('status', '').lower()
        payment_message = status_data.get('message', '')
        
        if payment_status == 'accepted':
            # Оплата успешна
            # Обновляем статусы заказов
            orders_sheet = get_orders_sheet()
            all_orders = orders_sheet.get_all_values()
            
            for order_id in payment_data['orders']:
                for idx, row in enumerate(all_orders):
                    if row[0] == order_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']:
                        # Обновляем статус заказа на "Оплачен"
                        orders_sheet.update_cell(idx + 1, 3, 'Оплачен')
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, payment_data.get('payment_id', ''), "оплачено")
            
            # Удаляем сообщение с QR-кодом, если оно есть
            try:
                if 'qr_message_id' in payment_data:
                    qr_message_id = payment_data['qr_message_id']
                    await context.bot.delete_message(
                        chat_id=chat_id,
                        message_id=qr_message_id
                    )
                    logger.info(f"Сообщение с QR-кодом {qr_message_id} успешно удалено после успешной оплаты")
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение с QR-кодом после успешной оплаты: {e}")
            
            # Отправляем сообщение об успешной оплате
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=buttons_message_id,
                text=translations.get_message('payment_success'),
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(chat_id)
            
            # Отменяем задачу
            return
            
        elif payment_status == 'rejected':
            # Платеж отклонен
            message_text = (
                f"Платеж отклонен.\n"
                f"Причина: {payment_message}\n\n"
                f"Попробуйте создать новый платеж или выберите другой способ оплаты."
            )
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, payment_data.get('payment_id', ''), "отклонено")
            
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=buttons_message_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(chat_id)
            
            # Отменяем задачу
            return
            
        elif payment_status == 'expired':
            # Время действия QR-кода истекло
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=buttons_message_id,
                text=translations.get_message('payment_expired'),
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(chat_id)
            
            # Отменяем задачу
            return
        
        # Для других статусов просто ждем, не обновляем сообщение
        # Состояние обновится при следующей попытке или пользователь может проверить вручную
            
    except Exception as e:
        logger.error(f"Ошибка при автоматической проверке статуса оплаты: {e}")

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
    
    # Получаем данные платежа из хранилища
    payment_data = get_payment(update.effective_chat.id)
    
    if not payment_data or 'qrc_id' not in payment_data:
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Данные о платеже не найдены. Попробуйте создать новый платеж.",
            reply_markup=reply_markup
        )
        return MENU
    
    # Проверяем наличие ID сообщения с кнопками
    if 'buttons_message_id' not in payment_data:
        # Если ID нет, создаем новое сообщение для кнопок
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        buttons_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Если оплата не подтвердилась автоматически, нажмите 'Проверить статус оплаты':",
            reply_markup=reply_markup
        )
        update_payment_message_ids(
            chat_id=update.effective_chat.id,
            buttons_message_id=buttons_message.message_id
        )
    
    # Временно редактируем сообщение, чтобы показать процесс проверки
    buttons_message_id = payment_data['buttons_message_id']
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=buttons_message_id,
        text=translations.get_message('payment_status_check')
    )
    
    try:
        # Проверяем статус оплаты
        qrc_id = payment_data['qrc_id']
        status_data = sbp.get_qr_code_status(qrc_id)
        
        # Логируем полный ответ для отладки
        logger.info(f"Получен ответ о статусе платежа: {status_data}")
        
        if not status_data:
            # Ошибка при получении статуса
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text="Не удалось получить статус оплаты. Попробуйте еще раз.",
                reply_markup=reply_markup
            )
            return PAYMENT
        
        # Проверяем статус платежа
        payment_status = status_data.get('status', '').lower()
        payment_message = status_data.get('message', '')
        
        logger.info(f"Статус платежа: {payment_status}, сообщение: {payment_message}")
        
        if payment_status == 'accepted':
            # Оплата успешна
            # Обновляем статусы заказов
            orders_sheet = get_orders_sheet()
            all_orders = orders_sheet.get_all_values()
            
            for order_id in payment_data['orders']:
                for idx, row in enumerate(all_orders):
                    if row[0] == order_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']:
                        # Обновляем статус заказа на "Оплачен"
                        orders_sheet.update_cell(idx + 1, 3, 'Оплачен')
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, payment_data.get('payment_id', ''), "оплачено")
            
            # Удаляем сообщение с QR-кодом, если оно есть
            try:
                if 'qr_message_id' in payment_data:
                    qr_message_id = payment_data['qr_message_id']
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=qr_message_id
                    )
                    logger.info(f"Сообщение с QR-кодом {qr_message_id} успешно удалено после успешной оплаты")
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение с QR-кодом после успешной оплаты: {e}")
            
            # Отправляем сообщение об успешной оплате
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
                [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=translations.get_message('payment_success'),
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(update.effective_chat.id)
            
            return MENU
            
        elif payment_status == 'expired':
            # Время действия QR-кода истекло
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=translations.get_message('payment_expired'),
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(update.effective_chat.id)
            
            return MENU
        
        elif payment_status == 'notstarted':
            # Платеж еще не начат
            message_text = (
                f"Платеж еще не начат. Пожалуйста, отсканируйте QR-код и выполните оплату.\n\n"
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
            # Пробуем запустить автоматическую проверку, если job_queue доступен
            try:
                auto_check_success = start_auto_check_payment(context, update.effective_chat.id, payment_data)
                if not auto_check_success:
                    logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
            except Exception as e:
                logger.warning(f"Не удалось запустить автоматическую проверку: {e}")
                # При ошибке просто продолжаем, пользователь может проверить статус вручную
            
            return PAYMENT
            
        elif payment_status == 'rejected':
            # Платеж отклонен
            message_text = (
                f"Платеж отклонен.\n"
                f"Причина: {payment_message}\n\n"
                f"Попробуйте создать новый платеж или выберите другой способ оплаты."
            )
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, payment_data.get('payment_id', ''), "отклонено")
            
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
            # Удаляем данные платежа из хранилища
            remove_payment(update.effective_chat.id)
                
            return MENU
        
        elif payment_status == 'pending':
            # Платеж в процессе
            message_text = (
                f"Платеж обрабатывается банком.\n"
                f"Пожалуйста, дождитесь завершения операции."
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
            # Пробуем запустить автоматическую проверку, если job_queue доступен
            try:
                auto_check_success = start_auto_check_payment(context, update.effective_chat.id, payment_data)
                if not auto_check_success:
                    logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
            except Exception as e:
                logger.warning(f"Не удалось запустить автоматическую проверку: {e}")
                # При ошибке просто продолжаем, пользователь может проверить статус вручную
            
            return PAYMENT
            
        else:
            # Другой статус (unknown и др.)
            message_text = (
                f"Ожидаем подтверждение оплаты...\n"
                f"Статус: {payment_status}\n"
                f"Сообщение: {payment_message}"
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
            # Пробуем запустить автоматическую проверку, если job_queue доступен
            try:
                auto_check_success = start_auto_check_payment(context, update.effective_chat.id, payment_data)
                if not auto_check_success:
                    logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
            except Exception as e:
                logger.warning(f"Не удалось запустить автоматическую проверку: {e}")
                # При ошибке просто продолжаем, пользователь может проверить статус вручную
            
            return PAYMENT
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса оплаты: {e}")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='check_payment')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='cancel_payment')]
        ]
        
        # Редактируем сообщение с кнопками
        if 'buttons_message_id' in payment_data:
            buttons_message_id = payment_data['buttons_message_id']
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=buttons_message_id,
                text="Произошла ошибка при проверке статуса оплаты. Попробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # Если ID сообщения с кнопками не найден, отправляем новое
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка при проверке статуса оплаты. Попробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        return PAYMENT

def start_auto_check_payment(context: ContextTypes.DEFAULT_TYPE, chat_id: int, payment_data: Dict[str, Any]) -> bool:
    """
    Запускает автоматическую проверку статуса платежа
    
    Args:
        context: Контекст бота
        chat_id: ID чата
        payment_data: Данные платежа
        
    Returns:
        bool: True если проверка успешно запущена, False в противном случае
    """
    if not context.job_queue:
        logger.warning("job_queue недоступен для автоматической проверки платежа")
        return False
    
    try:
        # Отменяем существующие задачи для этого чата
        job_name = f"payment_check_{chat_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
        
        # Создаем новую задачу
        context.job_queue.run_repeating(
            auto_check_payment_status,
            interval=STATUS_CHECK_INTERVAL,
            first=STATUS_CHECK_INTERVAL,
            name=job_name,
            data={'chat_id': chat_id}
        )
        
        logger.info(f"Запущена автоматическая проверка платежа для chat_id={chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при запуске автоматической проверки платежа: {e}")
        return False

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
    
    # Получаем данные платежа из хранилища
    payment_data = get_payment(update.effective_chat.id)
    
    if payment_data and 'payment_id' in payment_data:
        # Обновляем статус оплаты в таблице
        payments_sheet = get_payments_sheet()
        await update_payment_status(payments_sheet, payment_data['payment_id'], "отменено")
    
    # Останавливаем автоматическую проверку, если job_queue доступен
    if context.job_queue:
        try:
            job_name = f"payment_check_{update.effective_chat.id}"
            current_jobs = context.job_queue.get_jobs_by_name(job_name)
            for job in current_jobs:
                job.schedule_removal()
        except Exception as e:
            logger.warning(f"Ошибка при остановке автоматической проверки: {e}")
    else:
        logger.warning(f"job_queue недоступен при отмене платежа для chat_id={update.effective_chat.id}")
    
    # Удаляем сообщение с QR-кодом, если его ID есть в данных платежа
    try:
        if payment_data and 'qr_message_id' in payment_data:
            qr_message_id = payment_data['qr_message_id']
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=qr_message_id
            )
            logger.info(f"Сообщение с QR-кодом {qr_message_id} успешно удалено при отмене платежа")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с QR-кодом: {e}")
    
    # Проверяем наличие ID сообщения с кнопками в данных платежа
    if payment_data and 'buttons_message_id' in payment_data:
        buttons_message_id = payment_data['buttons_message_id']
        
        # Отправляем сообщение об отмене, редактируя только сообщение с кнопками
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=buttons_message_id,
            text=translations.get_message('payment_cancel'),
            reply_markup=reply_markup
        )
    else:
        # Если не можем найти ID сообщения с кнопками, редактируем текущее сообщение
        keyboard = [
            [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')],
            [InlineKeyboardButton(translations.get_button('new_order'), callback_data='new_order')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            translations.get_message('payment_cancel'),
            reply_markup=reply_markup
        )
    
    # Удаляем данные платежа из хранилища
    remove_payment(update.effective_chat.id)
    
    return MENU

async def update_payment_status(payments_sheet, payment_id: str, new_status: str) -> bool:
    """Обновляет статус оплаты в таблице.
    
    Args:
        payments_sheet: Лист с оплатами
        payment_id: Номер оплаты
        new_status: Новый статус
        
    Returns:
        bool: True в случае успешного обновления, False в противном случае
    """
    try:
        # Получаем все значения из таблицы
        all_payments = payments_sheet.get_all_values()
        
        # Ищем строку с нужным номером оплаты
        for idx, row in enumerate(all_payments[1:], start=2):  # Пропускаем заголовок
            if row[0] == payment_id:
                # Обновляем статус в последнем столбце
                payments_sheet.update_cell(idx, 6, new_status)
                logging.info(f"Статус оплаты {payment_id} обновлен на '{new_status}'")
                return True
                
        logging.warning(f"Оплата с номером {payment_id} не найдена в таблице")
        return False
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса оплаты: {e}")
        return False 