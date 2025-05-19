"""Тесты для обработчиков платежей."""
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from orderbot.handlers.payment import auto_check_payment_status, check_payment_status, update_payment_status
from orderbot.services.user import update_user_stats

# Настройка логгера для тестов
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

@pytest.fixture
def mock_update():
    """Фикстура для создания мока Update."""
    update = MagicMock(spec=Update)
    update.effective_chat.id = 123
    update.effective_user.id = 456
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    """Фикстура для создания мока Context."""
    context = MagicMock(spec=CallbackContext)
    context.bot = MagicMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.delete_message = AsyncMock()
    context.job_queue = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(return_value=[])
    return context

class MockUpdateUserStats(AsyncMock):
    """Специальный мок для отслеживания вызовов update_user_stats."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def __call__(self, *args, **kwargs):
        logger.debug(f"MockUpdateUserStats вызван с аргументами: {args}, {kwargs}")
        return await super().__call__(*args, **kwargs)

@pytest.mark.asyncio
async def test_auto_check_payment_status_updates_user_stats(mock_context):
    """Тест проверяет, что статистика пользователя обновляется после успешной оплаты в auto_check_payment_status."""
    logger.debug("Начинаем тест auto_check_payment_status_updates_user_stats")
    
    # Подготавливаем данные для теста
    job = MagicMock()
    job.data = {
        'chat_id': 123,
        'user_data': {
            'payment': {
                'qrc_id': 'test_qrc_id',
                'user_id': '456',
                'orders': ['1', '2'],
                'buttons_message_id': 789,
                'qr_message_id': 101,
                'status_checks': 0,
                'payment_id': '1'
            }
        }
    }
    mock_context.job = job

    # Мокаем ответ от API СБП
    with patch('orderbot.services.sbp.get_qr_code_status') as mock_get_status:
        logger.debug("Настраиваем мок для sbp.get_qr_code_status")
        mock_get_status.return_value = {
            'status': 'accepted',
            'message': 'Payment successful'
        }

        # Мокаем функции для работы с таблицами
        with patch('orderbot.services.sheets.get_orders_sheet') as mock_get_orders:
            logger.debug("Настраиваем мок для sheets.get_orders_sheet")
            mock_orders_sheet = MagicMock()
            mock_orders_sheet.get_all_values.return_value = [
                ['ID заказа', 'Время', 'Статус', 'User ID', 'Username', 'Сумма заказа', 'Номер комнаты', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
                ['1', '2023-01-01 12:00', 'Ожидает оплаты', '456', 'test_user', '1000', '101', 'Test User', 'breakfast', 'Блюдо 1', 'Нет', '2023-01-02'],
                ['2', '2023-01-01 12:00', 'Ожидает оплаты', '456', 'test_user', '1000', '101', 'Test User', 'breakfast', 'Блюдо 2', 'Нет', '2023-01-02']
            ]
            mock_get_orders.return_value = mock_orders_sheet

        with patch('orderbot.services.sheets.get_payments_sheet') as mock_get_payments:
            logger.debug("Настраиваем мок для sheets.get_payments_sheet")
            mock_payments_sheet = MagicMock()
            mock_get_payments.return_value = mock_payments_sheet

        # Мокаем функцию обновления статуса платежа
        with patch('orderbot.handlers.payment.update_payment_status') as mock_update_payment_status:
            logger.debug("Настраиваем мок для payment.update_payment_status")
            mock_update_payment_status.return_value = True
            
            # Мокаем все асинхронные методы контекста
            mock_context.bot.send_message = AsyncMock()
            mock_context.bot.send_photo = AsyncMock()

            # Мокаем функцию обновления статистики пользователя с отладочной информацией
            mock_update_stats = MockUpdateUserStats()
            with patch('orderbot.services.user.update_user_stats', mock_update_stats):
                logger.debug("Настраиваем мок для user.update_user_stats")
                
                # Вызываем тестируемую функцию
                logger.debug("Вызываем auto_check_payment_status")
                await auto_check_payment_status(mock_context)
                
                # Проверяем логи вызовов
                logger.debug(f"Вызовы update_user_stats: {mock_update_stats.mock_calls}")
                
                # Проверяем, что функция обновления статистики была вызвана с правильным ID пользователя
                mock_update_stats.assert_called_once_with('456')

@pytest.mark.asyncio
async def test_check_payment_status_updates_user_stats(mock_update, mock_context):
    """Тест проверяет, что статистика пользователя обновляется после успешной оплаты в check_payment_status."""
    logger.debug("Начинаем тест check_payment_status_updates_user_stats")
    
    # Подготавливаем данные для теста
    mock_context.user_data = {
        'payment': {
            'qrc_id': 'test_qrc_id',
            'user_id': '456',
            'orders': ['1', '2'],
            'buttons_message_id': 789,
            'qr_message_id': 101,
            'status_checks': 0,
            'payment_id': '1'
        }
    }

    # Мокаем ответ от API СБП
    with patch('orderbot.services.sbp.get_qr_code_status') as mock_get_status:
        logger.debug("Настраиваем мок для sbp.get_qr_code_status")
        mock_get_status.return_value = {
            'status': 'accepted',
            'message': 'Payment successful'
        }

        # Мокаем функции для работы с таблицами
        with patch('orderbot.services.sheets.get_orders_sheet') as mock_get_orders:
            logger.debug("Настраиваем мок для sheets.get_orders_sheet")
            mock_orders_sheet = MagicMock()
            mock_orders_sheet.get_all_values.return_value = [
                ['ID заказа', 'Время', 'Статус', 'User ID', 'Username', 'Сумма заказа', 'Номер комнаты', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
                ['1', '2023-01-01 12:00', 'Ожидает оплаты', '456', 'test_user', '1000', '101', 'Test User', 'breakfast', 'Блюдо 1', 'Нет', '2023-01-02'],
                ['2', '2023-01-01 12:00', 'Ожидает оплаты', '456', 'test_user', '1000', '101', 'Test User', 'breakfast', 'Блюдо 2', 'Нет', '2023-01-02']
            ]
            mock_get_orders.return_value = mock_orders_sheet

        with patch('orderbot.services.sheets.get_payments_sheet') as mock_get_payments:
            logger.debug("Настраиваем мок для sheets.get_payments_sheet")
            mock_payments_sheet = MagicMock()
            mock_get_payments.return_value = mock_payments_sheet
            
        # Мокаем все асинхронные методы контекста
        mock_context.bot.send_message = AsyncMock()
        mock_context.bot.edit_message_text = AsyncMock()

        # Мокаем функцию обновления статуса платежа
        with patch('orderbot.handlers.payment.update_payment_status') as mock_update_payment_status:
            logger.debug("Настраиваем мок для payment.update_payment_status")
            mock_update_payment_status.return_value = True
            
            # Мокаем функцию stop_auto_check_payment
            with patch('orderbot.handlers.payment.stop_auto_check_payment') as mock_stop_auto_check:
                logger.debug("Настраиваем мок для payment.stop_auto_check_payment")
                mock_stop_auto_check.return_value = True

                # Мокаем функцию обновления статистики пользователя с отладочной информацией
                mock_update_stats = MockUpdateUserStats()
                with patch('orderbot.services.user.update_user_stats', mock_update_stats):
                    logger.debug("Настраиваем мок для user.update_user_stats")
                    
                    # Вызываем тестируемую функцию
                    logger.debug("Вызываем check_payment_status")
                    await check_payment_status(mock_update, mock_context)
                    
                    # Проверяем логи вызовов
                    logger.debug(f"Вызовы update_user_stats: {mock_update_stats.mock_calls}")
                    
                    # Проверяем, что функция обновления статистики была вызвана с правильным ID пользователя
                    mock_update_stats.assert_called_once_with('456') 