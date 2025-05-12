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

# Настройка логгера
logger = logging.getLogger(__name__)

# Максимальное число попыток проверки статуса
MAX_STATUS_CHECKS = 20
# Интервал между проверками в секундах
STATUS_CHECK_INTERVAL = 15

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
    user_orders = [row for row in all_orders[1:] if row[3] == user_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']]
    
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
    
    # Получаем номер комнаты из первого заказа пользователя
    room_number = user_orders[0][6] if user_orders and len(user_orders[0]) > 6 else ""
    
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
    payment_purpose = f"Оплата заказа (комната {room_number})" if room_number else "Оплата заказа"
    
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
        
        # Сохраняем информацию об оплате в таблицу
        payment_saved = await save_payment_info(
            user_id=str(update.effective_user.id),
            amount=total_sum,
            status="ожидает",
            room=room_number
        )
        
        if not payment_saved:
            logger.error("Не удалось сохранить информацию об оплате в таблицу")
            keyboard = [
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                translations.get_message('payment_error'),
                reply_markup=reply_markup
            )
            return MENU
        
        # Получаем ID последней сохраненной оплаты
        payments_sheet = get_payments_sheet()
        all_payments = payments_sheet.get_all_values()
        last_payment_id = all_payments[-1][0] if len(all_payments) > 1 else "1"
        
        # Сохраняем данные о платеже в контексте
        context.user_data['payment'] = {
            'qrc_id': qr_data['qrcId'],
            'amount': total_sum,
            'orders': [order[0] for order in user_orders],  # Список ID заказов
            'created_at': datetime.now().isoformat(),
            'payload': qr_data.get('payload', ''),
            'status_checks': 0,  # Счетчик проверок статуса
            'payment_id': last_payment_id,  # ID оплаты в таблице
            'chat_id': update.effective_chat.id,  # Сохраняем ID чата
            'room': room_number  # Сохраняем номер комнаты
        }
        
        # Декодируем изображение QR-кода из base64
        qr_image_data = qr_data.get('image', {}).get('content', '')
        if qr_image_data:
            try:
                # Удаляем префикс data:image/png;base64, если он есть
                if isinstance(qr_image_data, str) and ',' in qr_image_data:
                    qr_image_data = qr_image_data.split(',', 1)[1]
                
                # Декодируем base64 в бинарные данные
                image_bytes = base64.b64decode(qr_image_data)
                image = Image.open(io.BytesIO(image_bytes))
                
                # Сохраняем изображение во временный файл
                buffer = io.BytesIO()
                image.save(buffer, format='PNG')
                buffer.seek(0)
                
                # Формируем сообщение с QR-кодом и суммой (выделенной жирным)
                message_text = (
                    f"{translations.get_message('payment_qr_created')}\n\n"
                    f"Сумма к оплате: *{total_sum} руб.*\n\n"
                )
                
                # Добавляем ссылку на оплату, если она есть
                payment_url = context.user_data['payment'].get('payload', '')
                if payment_url:
                    message_text += f"Также можете оплатить по ссылке: {payment_url}\n\n"
                
                message_text += translations.get_message('payment_instructions')
                
                # Удаляем старое сообщение
                await query.delete_message()
                
                # 1. Отправляем сообщение с QR-кодом и информацией о платеже (без кнопок)
                # Используем parse_mode=MarkdownV2 для выделения суммы жирным шрифтом
                qr_message = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=buffer,
                    caption=message_text,
                    parse_mode='Markdown'  # Используем Markdown для выделения жирным
                )
                
                # 2. Отправляем отдельное сообщение с кнопками управления платежом
                keyboard = [
                    [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                    [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Сохраняем ID сообщения с кнопками в контексте пользователя
                buttons_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Если оплата не подтвердилась автоматически, нажмите на кнопку 'Проверить статус оплаты':",
                    reply_markup=reply_markup
                )
                
                # Сохраняем ID обоих сообщений в контексте
                context.user_data['payment']['qr_message_id'] = qr_message.message_id
                context.user_data['payment']['buttons_message_id'] = buttons_message.message_id
                
                # Запускаем автоматическую проверку статуса платежа
                try:
                    auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
                    if not auto_check_success:
                        logger.info(f"Не удалось запустить автоматическую проверку платежа при создании")
                except Exception as e:
                    logger.error(f"Ошибка при запуске автоматической проверки платежа: {e}")
                
                return PAYMENT
                
            except Exception as e:
                logger.error(f"Ошибка при обработке изображения QR-кода: {e}")
                
                # В случае ошибки с изображением отправляем текстовое сообщение с информацией
                message_text = (
                    f"{translations.get_message('payment_qr_created')}\n\n"
                    f"Сумма к оплате: *{total_sum} руб.*\n\n"
                )
                
                # Добавляем ссылку на оплату, если она есть
                payment_url = context.user_data['payment'].get('payload', '')
                if payment_url:
                    message_text += f"Также можете оплатить по ссылке: {payment_url}\n\n"
                
                message_text += translations.get_message('payment_instructions')
                
                # 1. Отправляем текстовое сообщение с информацией о платеже
                await query.delete_message()
                qr_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                
                # 2. Отправляем отдельное сообщение с кнопками управления платежом
                keyboard = [
                    [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                    [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                buttons_message = await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Если оплата не подтвердилась автоматически, нажмите 'Проверить статус оплаты':",
                    reply_markup=reply_markup
                )
                
                # Сохраняем ID обоих сообщений в контексте
                context.user_data['payment']['qr_message_id'] = qr_message.message_id
                context.user_data['payment']['buttons_message_id'] = buttons_message.message_id
                
                # Запускаем автоматическую проверку статуса платежа
                try:
                    auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
                    if not auto_check_success:
                        logger.info(f"Не удалось запустить автоматическую проверку платежа при создании")
                except Exception as e:
                    logger.error(f"Ошибка при запуске автоматической проверки платежа: {e}")
                
                return PAYMENT
        
        # Если изображения нет, отправляем только текст со ссылкой
        message_text = (
            f"{translations.get_message('payment_qr_created')}\n\n"
            f"Сумма к оплате: *{total_sum} руб.*\n\n"
        )
        
        # Добавляем ссылку на оплату, если она есть
        payment_url = context.user_data['payment'].get('payload', '')
        if payment_url:
            message_text += f"Также можете оплатить по ссылке: {payment_url}\n\n"
        
        message_text += translations.get_message('payment_instructions')
        
        # 1. Отправляем текстовое сообщение с информацией о платеже
        await query.delete_message()
        qr_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            parse_mode='Markdown'
        )
        
        # 2. Отправляем отдельное сообщение с кнопками управления платежом
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        buttons_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Если оплата не подтвердилась автоматически, нажмите 'Проверить статус оплаты':",
            reply_markup=reply_markup
        )
        
        # Сохраняем ID обоих сообщений в контексте
        context.user_data['payment']['qr_message_id'] = qr_message.message_id
        context.user_data['payment']['buttons_message_id'] = buttons_message.message_id
        
        # Запускаем автоматическую проверку статуса платежа
        try:
            auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
            if not auto_check_success:
                logger.info(f"Не удалось запустить автоматическую проверку платежа при создании")
        except Exception as e:
            logger.error(f"Ошибка при запуске автоматической проверки платежа: {e}")
        
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

# Функция для автоматической проверки статуса платежа
async def auto_check_payment_status(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Автоматически проверяет статус оплаты с заданным интервалом
    
    Args:
        context: Контекст бота
    """
    job = context.job
    chat_id = job.data['chat_id']
    user_data = job.data['user_data']
    
    try:
        # Проверяем, есть ли данные о платеже
        if 'payment' not in user_data or 'qrc_id' not in user_data['payment']:
            # Платеж не найден, отменяем задачу
            logger.info(f"Автопроверка: данные о платеже не найдены")
            # Останавливаем задачу автопроверки
            try:
                job_name = f"payment_check_{chat_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                logger.info(f"Автопроверка: задача остановлена из-за отсутствия данных о платеже")
            except Exception as e:
                logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
            return
        
        # Увеличиваем счетчик проверок
        user_data['payment']['status_checks'] += 1
        
        # Проверяем наличие ID сообщения с кнопками
        if 'buttons_message_id' not in user_data['payment']:
            logger.warning(f"Автопроверка: не найден ID сообщения с кнопками")
            return
            
        buttons_message_id = user_data['payment']['buttons_message_id']
        
        # Проверяем, не превышено ли максимальное число попыток
        if user_data['payment']['status_checks'] > MAX_STATUS_CHECKS:
            logger.info(f"Автопроверка: достигнуто максимальное число попыток ({MAX_STATUS_CHECKS})")
            
            # Отправляем сообщение о превышении числа попыток
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=buttons_message_id,
                    text="Автоматическая проверка завершена. Нажмите кнопку для ручной проверки статуса.",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при автоматической проверке статуса оплаты: {e}")
            
            # Останавливаем задачу автопроверки - ВАЖНО!
            try:
                job_name = f"payment_check_{chat_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                logger.info(f"Автопроверка: задача остановлена после достижения максимального числа попыток")
            except Exception as e:
                logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
                
            # Отменяем задачу
            return
        
        # Проверяем статус оплаты
        qrc_id = user_data['payment']['qrc_id']
        logger.info(f"Автопроверка: запрос статуса QR-кода {qrc_id}, попытка {user_data['payment']['status_checks']}")
        
        status_data = sbp.get_qr_code_status(qrc_id)
        
        if not status_data:
            logger.warning(f"Автопроверка: не удалось получить статус оплаты")
            return
        
        # Проверяем статус платежа
        payment_status = status_data.get('status', '').lower()
        payment_message = status_data.get('message', '')
        
        logger.info(f"Автопроверка: статус платежа {payment_status}, сообщение: {payment_message}")
        
        # Проверяем время жизни QR-кода (обычно 5 минут = 300 секунд)
        # Если прошло больше 5 минут с момента создания и статус все еще notstarted,
        # считаем QR-код истекшим и завершаем проверку
        if payment_status == 'notstarted' and 'created_at' in user_data['payment']:
            try:
                created_at = datetime.fromisoformat(user_data['payment']['created_at'])
                now = datetime.now()
                delta = now - created_at
                
                # Проверяем, прошло ли 10 минут (600 секунд) с момента создания QR-кода
                if delta.total_seconds() > 600:
                    logger.info(f"Автопроверка: QR-код истек по времени (прошло {delta.total_seconds()} секунд)")
                    
                    # Обновляем статус оплаты в таблице
                    payments_sheet = get_payments_sheet()
                    await update_payment_status(payments_sheet, user_data['payment'].get('payment_id', ''), "истек срок")
                    
                    # Отправляем сообщение об истечении срока
                    keyboard = [
                        [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=buttons_message_id,
                            text=translations.get_message('payment_expired'),
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        logger.error(f"Ошибка при обновлении сообщения об истечении срока QR-кода: {e}")
                    
                    # Останавливаем задачу автопроверки
                    try:
                        job_name = f"payment_check_{chat_id}"
                        current_jobs = context.job_queue.get_jobs_by_name(job_name)
                        for job in current_jobs:
                            job.schedule_removal()
                        logger.info(f"Автопроверка: задача остановлена, QR-код истек по времени")
                    except Exception as e:
                        logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
                    
                    # Очищаем данные о платеже
                    if 'payment' in user_data:
                        del user_data['payment']
                    
                    # Отменяем задачу
                    return
            except Exception as e:
                logger.error(f"Ошибка при проверке времени жизни QR-кода: {e}")
            
        if payment_status == 'accepted':
            # Оплата успешна, обновляем статусы заказов
            orders_sheet = get_orders_sheet()
            all_orders = orders_sheet.get_all_values()
            
            for order_id in user_data['payment']['orders']:
                for idx, row in enumerate(all_orders):
                    if row[0] == order_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']:
                        # Обновляем статус заказа на "Оплачен"
                        orders_sheet.update_cell(idx + 1, 3, 'Оплачен')
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, user_data['payment'].get('payment_id', ''), "оплачено")
            
            # Удаляем сообщение с QR-кодом, если оно есть
            try:
                if 'qr_message_id' in user_data['payment']:
                    qr_message_id = user_data['payment']['qr_message_id']
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
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=buttons_message_id,
                    text=translations.get_message('payment_success'),
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об успешной оплате: {e}")
            
            # Останавливаем задачу автопроверки
            try:
                job_name = f"payment_check_{chat_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                logger.info(f"Автопроверка: задача остановлена, платеж успешно выполнен")
            except Exception as e:
                logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
            
            # Очищаем данные о платеже
            if 'payment' in user_data:
                del user_data['payment']
            
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
            await update_payment_status(payments_sheet, user_data['payment'].get('payment_id', ''), "отклонено")
            
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Обновляем сообщение с кнопками
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=buttons_message_id,
                    text=message_text,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об отклонении платежа: {e}")
            
            # Останавливаем задачу автопроверки
            try:
                job_name = f"payment_check_{chat_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                logger.info(f"Автопроверка: задача остановлена, платеж отклонен")
            except Exception as e:
                logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
            
            # Очищаем данные о платеже
            if 'payment' in user_data:
                del user_data['payment']
            
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
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=buttons_message_id,
                    text=translations.get_message('payment_expired'),
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об истечении срока QR-кода: {e}")
            
            # Останавливаем задачу автопроверки
            try:
                job_name = f"payment_check_{chat_id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                for job in current_jobs:
                    job.schedule_removal()
                logger.info(f"Автопроверка: задача остановлена, QR-код истек")
            except Exception as e:
                logger.error(f"Ошибка при остановке задачи автопроверки: {e}")
            
            # Очищаем данные о платеже
            if 'payment' in user_data:
                del user_data['payment']
            
            # Отменяем задачу
            return
            
        # Для других статусов (pending, notstarted и т.д.) просто продолжаем проверку
        # Не перезапускаем check_payment, продолжаем текущий цикл проверки
            
    except Exception as e:
        logger.error(f"Ошибка при автоматической проверке статуса оплаты: {e}")
        # При ошибке просто продолжаем, следующая проверка будет по расписанию

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
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Данные о платеже не найдены. Попробуйте создать новый платеж.",
            reply_markup=reply_markup
        )
        return MENU
    
    # Проверяем наличие ID сообщения с кнопками в контексте
    if 'buttons_message_id' not in context.user_data['payment']:
        # Если ID нет в контексте, создаем новое сообщение для кнопок
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        buttons_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Если оплата не подтвердилась автоматически, нажмите 'Проверить статус оплаты':",
            reply_markup=reply_markup
        )
        context.user_data['payment']['buttons_message_id'] = buttons_message.message_id
    
    # Временно редактируем сообщение, чтобы показать процесс проверки
    buttons_message_id = context.user_data['payment']['buttons_message_id']
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=buttons_message_id,
        text=translations.get_message('payment_status_check')
    )
    
    try:
        # Проверяем статус оплаты
        qrc_id = context.user_data['payment']['qrc_id']
        status_data = sbp.get_qr_code_status(qrc_id)
        
        # Логируем полный ответ для отладки
        logger.info(f"Получен ответ о статусе платежа: {status_data}")
        
        if not status_data:
            # Ошибка при получении статуса
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
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
            
            for order_id in context.user_data['payment']['orders']:
                for idx, row in enumerate(all_orders):
                    if row[0] == order_id and row[2] in ['Принят', 'Активен', 'Ожидает оплаты']:
                        # Обновляем статус заказа на "Оплачен"
                        orders_sheet.update_cell(idx + 1, 3, 'Оплачен')
            
            # Обновляем статус оплаты в таблице
            payments_sheet = get_payments_sheet()
            await update_payment_status(payments_sheet, context.user_data['payment'].get('payment_id', ''), "оплачено")
            
            # Удаляем сообщение с QR-кодом, если оно есть
            try:
                if 'qr_message_id' in context.user_data['payment']:
                    qr_message_id = context.user_data['payment']['qr_message_id']
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
            
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=buttons_message_id,
                    text=translations.get_message('payment_success'),
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об успешной оплате: {e}")
            
            # Останавливаем автоматическую проверку статуса платежа
            stop_auto_check_payment(context, update.effective_chat.id)
            
            return MENU
            
        elif payment_status == 'expired':
            # Время действия QR-кода истекло
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=buttons_message_id,
                    text=translations.get_message('payment_expired'),
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об истечении срока QR-кода: {e}")
            
            # Очищаем данные о платеже
            if 'payment' in context.user_data:
                del context.user_data['payment']
                
            # Останавливаем автоматическую проверку статуса платежа
            stop_auto_check_payment(context, update.effective_chat.id)
            
            return MENU
        
        elif payment_status == 'notstarted':
            # Платеж еще не начат
            message_text = (
                f"Платеж еще не начат. Пожалуйста, отсканируйте QR-код и выполните оплату.\n\n"
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
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
                # Проверяем, не запущена ли уже задача автопроверки
                job_name = f"payment_check_{update.effective_chat.id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                
                if not current_jobs:
                    # Задача не запущена, запускаем новую
                    auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
                    if not auto_check_success:
                        logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
                else:
                    logger.info(f"Задача автопроверки уже запущена для chat_id={update.effective_chat.id}, не запускаем повторно")
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
            await update_payment_status(payments_sheet, context.user_data['payment'].get('payment_id', ''), "отклонено")
            
            keyboard = [
                [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
                [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=buttons_message_id,
                    text=message_text,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении сообщения об отклонении платежа: {e}")
            
            # Останавливаем автоматическую проверку статуса платежа
            stop_auto_check_payment(context, update.effective_chat.id)
            
            return MENU
        
        elif payment_status == 'pending':
            # Платеж в процессе
            message_text = (
                f"Платеж обрабатывается банком.\n"
                f"Пожалуйста, дождитесь завершения операции."
            )
            keyboard = [
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
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
                # Проверяем, не запущена ли уже задача автопроверки
                job_name = f"payment_check_{update.effective_chat.id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                
                if not current_jobs:
                    # Задача не запущена, запускаем новую
                    auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
                    if not auto_check_success:
                        logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
                else:
                    logger.info(f"Задача автопроверки уже запущена для chat_id={update.effective_chat.id}, не запускаем повторно")
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
                [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
                [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
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
                # Проверяем, не запущена ли уже задача автопроверки
                job_name = f"payment_check_{update.effective_chat.id}"
                current_jobs = context.job_queue.get_jobs_by_name(job_name)
                
                if not current_jobs:
                    # Задача не запущена, запускаем новую
                    auto_check_success = start_auto_check_payment(context, update.effective_chat.id, context.user_data)
                    if not auto_check_success:
                        logger.info("Автоматическая проверка не запущена. Пользователь должен проверить статус вручную.")
                else:
                    logger.info(f"Задача автопроверки уже запущена для chat_id={update.effective_chat.id}, не запускаем повторно")
            except Exception as e:
                logger.warning(f"Не удалось запустить автоматическую проверку: {e}")
                # При ошибке просто продолжаем, пользователь может проверить статус вручную
            
            return PAYMENT
            
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса оплаты: {e}")
        keyboard = [
            [InlineKeyboardButton(translations.get_button('check_payment'), callback_data='payment:check')],
            [InlineKeyboardButton(translations.get_button('cancel_payment'), callback_data='payment:cancel')]
        ]
        
        # Редактируем сообщение с кнопками
        if 'buttons_message_id' in context.user_data.get('payment', {}):
            buttons_message_id = context.user_data['payment']['buttons_message_id']
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

def start_auto_check_payment(context, chat_id, user_data):
    """
    Запускает автоматическую проверку статуса платежа
    
    Args:
        context: Контекст бота
        chat_id: ID чата
        user_data: Данные пользователя
        
    Returns:
        bool: True если задача успешно запущена, False в противном случае
    """
    # Проверяем, доступна ли job_queue в контексте
    if not context.job_queue:
        logger.warning(f"job_queue недоступен в контексте, автоматическая проверка невозможна для chat_id={chat_id}")
        return False
        
    # Сначала остановим предыдущие задачи с этим именем, если они есть
    try:
        job_name = f"payment_check_{chat_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
        
        # Запускаем новую задачу
        context.job_queue.run_repeating(
            auto_check_payment_status,
            interval=STATUS_CHECK_INTERVAL,
            first=STATUS_CHECK_INTERVAL,
            data={
                'chat_id': chat_id,
                'user_data': user_data
            },
            name=job_name
        )
        logger.info(f"Запущена автоматическая проверка статуса платежа для chat_id={chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при настройке автоматической проверки статуса: {e}")
        return False

def stop_auto_check_payment(context, chat_id):
    """
    Останавливает автоматическую проверку статуса платежа
    
    Args:
        context: Контекст бота
        chat_id: ID чата
        
    Returns:
        bool: True если задача успешно остановлена, False в противном случае
    """
    # Проверяем, доступна ли job_queue в контексте
    if not context.job_queue:
        logger.warning(f"job_queue недоступен в контексте, невозможно остановить автопроверку для chat_id={chat_id}")
        return False
        
    try:
        job_name = f"payment_check_{chat_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        if not current_jobs:
            logger.info(f"Нет активных задач автопроверки для chat_id={chat_id}")
            return True
            
        for job in current_jobs:
            job.schedule_removal()
        
        logger.info(f"Остановлена автоматическая проверка статуса платежа для chat_id={chat_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при остановке автоматической проверки статуса: {e}")
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
    
    # Проверяем, есть ли данные о платеже
    if 'payment' not in context.user_data or 'qrc_id' not in context.user_data['payment']:
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
    
    # Останавливаем автоматическую проверку статуса платежа
    stop_auto_check_payment(context, update.effective_chat.id)
    
    # Обновляем статус оплаты в таблице
    try:
        payments_sheet = get_payments_sheet()
        await update_payment_status(payments_sheet, context.user_data['payment'].get('payment_id', ''), "отменено")
        logger.info(f"Статус платежа {context.user_data['payment'].get('payment_id', '')} обновлен на 'отменено'")
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса оплаты в таблице: {e}")
    
    # Удаляем сообщение с QR-кодом, если оно есть
    try:
        if 'qr_message_id' in context.user_data['payment']:
            qr_message_id = context.user_data['payment']['qr_message_id']
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=qr_message_id
            )
            logger.info(f"Сообщение с QR-кодом {qr_message_id} успешно удалено после отмены оплаты")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение с QR-кодом после отмены оплаты: {e}")
    
    # Отправляем сообщение об отмене оплаты
    keyboard = [
        [InlineKeyboardButton(translations.get_button('pay_orders'), callback_data='pay_orders')],
        [InlineKeyboardButton(translations.get_button('my_orders'), callback_data='my_orders')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Обновляем сообщение с кнопками или отправляем новое
    try:
        if 'buttons_message_id' in context.user_data['payment']:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['payment']['buttons_message_id'],
                    text=translations.get_message('payment_cancel'),
                    reply_markup=reply_markup
                )
                logger.info(f"Сообщение об отмене платежа успешно отображено")
            except telegram.error.BadRequest as e:
                if "Message is not modified" in str(e):
                    # Если сообщение не изменилось, просто логируем и продолжаем
                    logger.warning(f"Сообщение с кнопками не изменилось: {e}")
                else:
                    # Если другая ошибка, пробуем отправить новое сообщение
                    logger.warning(f"Не удалось обновить сообщение с кнопками: {e}")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=translations.get_message('payment_cancel'),
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.warning(f"Не удалось обновить сообщение с кнопками: {e}")
                # Если не удалось обновить, отправляем новое сообщение
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=translations.get_message('payment_cancel'),
                    reply_markup=reply_markup
                )
        else:
            # Если ID сообщения не найден, отправляем новое
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=translations.get_message('payment_cancel'),
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения об отмене платежа: {e}")
    
    # Очищаем данные о платеже
    if 'payment' in context.user_data:
        del context.user_data['payment']
        logger.info(f"Данные о платеже удалены из контекста пользователя")
    
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
                # Обновляем статус в столбце 6 (F)
                payments_sheet.update_cell(idx, 6, new_status)
                logging.info(f"Статус оплаты {payment_id} обновлен на '{new_status}'")
                return True
                
        logging.warning(f"Оплата с номером {payment_id} не найдена в таблице")
        return False
    except Exception as e:
        logging.error(f"Ошибка при обновлении статуса оплаты: {e}")
        return False

@require_auth
async def handle_payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обрабатывает действия с платежом (проверка статуса, отмена)
    
    Args:
        update: Объект обновления от Telegram
        context: Контекст бота
        
    Returns:
        int: Следующее состояние беседы
    """
    query = update.callback_query
    await query.answer()
    
    try:
        action = query.data.split(':')[1]
        
        if action == 'check':
            return await check_payment_status(update, context)
        elif action == 'cancel':
            return await cancel_payment(update, context)
        else:
            logger.warning(f"Неизвестное действие с платежом: {action}")
            return PAYMENT
            
    except Exception as e:
        logger.error(f"Ошибка при обработке действия с платежом: {e}")
        return PAYMENT 