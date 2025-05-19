"""Тесты для обработчиков платежей."""
import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from orderbot.handlers.payment import auto_check_payment_status, check_payment_status

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

@pytest.mark.asyncio
async def test_auto_check_payment_status_exists():
    """Тест проверяет существование функции auto_check_payment_status."""
    assert callable(auto_check_payment_status)

@pytest.mark.asyncio
async def test_check_payment_status_exists():
    """Тест проверяет существование функции check_payment_status."""
    assert callable(check_payment_status)

@pytest.mark.asyncio
async def test_auto_check_payment_status_handles_success():
    """Тест проверяет обработку успешного платежа в auto_check_payment_status."""
    # Создаем мок для контекста
    mock_context = MagicMock()
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.delete_message = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Создаем мок для job
    job = MagicMock()
    user_data = {
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
    job.data = {
        'chat_id': 123,
        'user_data': user_data
    }
    mock_context.job = job
    
    # Мокаем все внешние функции
    with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'accepted', 'message': 'Payment successful'}):
        # Мокаем таблицы и другие внешние зависимости
        with patch('orderbot.services.sheets.get_orders_sheet'):
            with patch('orderbot.services.sheets.get_payments_sheet'):
                with patch('orderbot.handlers.payment.update_payment_status'):
                    with patch('orderbot.services.user.update_user_stats'):
                        # Вызываем функцию
                        await auto_check_payment_status(mock_context)
                        
                        # Проверяем, что оповещение об успешной оплате было отправлено
                        assert mock_context.bot.edit_message_text.called or mock_context.bot.send_message.called

@pytest.mark.asyncio
async def test_check_payment_status_handles_accepted_payment():
    """Тест проверяет обработку успешного платежа в check_payment_status."""
    # Создаем мок для update
    mock_update = MagicMock(spec=Update)
    mock_update.effective_chat.id = 123
    mock_update.callback_query = AsyncMock()
    
    # Создаем мок для контекста
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
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
    
    # Мокаем все внешние функции
    with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'accepted', 'message': 'Payment successful'}):
        with patch('orderbot.services.sheets.get_orders_sheet'):
            with patch('orderbot.services.sheets.get_payments_sheet'):
                with patch('orderbot.handlers.payment.update_payment_status'):
                    with patch('orderbot.services.user.update_user_stats'):
                        with patch('orderbot.handlers.payment.stop_auto_check_payment'):
                            # Вызываем функцию
                            result = await check_payment_status(mock_update, mock_context)
                            
                            # Проверяем, что сообщение было обновлено
                            assert mock_context.bot.edit_message_text.called

@pytest.mark.asyncio
async def test_auto_check_payment_status_handles_rejected():
    """Тест проверяет обработку отклоненного платежа в auto_check_payment_status."""
    # Создаем мок для контекста
    mock_context = MagicMock()
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.delete_message = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Создаем мок для job
    job = MagicMock()
    user_data = {
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
    job.data = {
        'chat_id': 123,
        'user_data': user_data
    }
    mock_context.job = job
    
    # Мокаем все внешние функции
    with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'rejected', 'message': 'Payment rejected'}):
        # Мокаем таблицы и другие внешние зависимости
        with patch('orderbot.services.sheets.get_orders_sheet'):
            with patch('orderbot.services.sheets.get_payments_sheet'):
                with patch('orderbot.handlers.payment.update_payment_status'):
                    # Вызываем функцию
                    await auto_check_payment_status(mock_context)
                    
                    # Проверяем, что сообщение об отклонении было отправлено
                    assert mock_context.bot.edit_message_text.called or mock_context.bot.send_message.called

@pytest.mark.asyncio
async def test_check_payment_status_handles_expired_payment():
    """Тест проверяет обработку истекшего платежа в check_payment_status."""
    # Создаем мок для update
    mock_update = MagicMock(spec=Update)
    mock_update.effective_chat.id = 123
    mock_update.callback_query = AsyncMock()
    
    # Создаем мок для контекста
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
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
    
    # Мокаем все внешние функции
    with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'expired', 'message': 'QR code expired'}):
        with patch('orderbot.services.sheets.get_orders_sheet'):
            with patch('orderbot.services.sheets.get_payments_sheet'):
                with patch('orderbot.handlers.payment.update_payment_status'):
                    with patch('orderbot.handlers.payment.stop_auto_check_payment'):
                        # Вызываем функцию
                        result = await check_payment_status(mock_update, mock_context)
                        
                        # Проверяем, что сообщение было обновлено
                        assert mock_context.bot.edit_message_text.called

@pytest.mark.asyncio
async def test_check_payment_status_handles_missing_payment_data():
    """Тест проверяет обработку отсутствующих данных платежа в check_payment_status."""
    # Создаем мок для update
    mock_update = MagicMock(spec=Update)
    mock_update.effective_chat.id = 123
    mock_update.callback_query = AsyncMock()
    
    # Создаем мок для контекста без данных платежа
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = MagicMock()
    mock_context.bot.send_message = AsyncMock()
    mock_context.user_data = {}  # Пустой словарь, без данных о платеже
    
    # Вызываем функцию
    result = await check_payment_status(mock_update, mock_context)
    
    # Проверяем, что отправлено сообщение об отсутствии данных платежа
    assert mock_context.bot.send_message.called 

@pytest.mark.asyncio
async def test_update_user_stats_is_called_after_successful_payment():
    """Тест проверяет вызов update_user_stats после успешной оплаты."""
    # Создаем мок для update
    mock_update = MagicMock(spec=Update)
    mock_update.effective_chat.id = 123
    mock_update.callback_query = AsyncMock()
    
    # Создаем мок для контекста
    mock_context = MagicMock(spec=CallbackContext)
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Создаем данные платежа с тестовым user_id
    test_user_id = '456'
    mock_context.user_data = {
        'payment': {
            'qrc_id': 'test_qrc_id',
            'user_id': test_user_id,
            'orders': ['1', '2'],
            'buttons_message_id': 789,
            'qr_message_id': 101,
            'status_checks': 0,
            'payment_id': '1'
        }
    }
    
    # Создаем мок для update_user_stats
    with patch('orderbot.services.user.update_user_stats') as mock_update_user_stats:
        # Настраиваем mock_update_user_stats.return_value
        mock_update_user_stats.return_value = True
        
        # Мокаем остальные внешние функции
        with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'accepted', 'message': 'Payment successful'}):
            with patch('orderbot.services.sheets.get_orders_sheet'):
                with patch('orderbot.services.sheets.get_payments_sheet'):
                    with patch('orderbot.handlers.payment.update_payment_status'):
                        with patch('orderbot.handlers.payment.stop_auto_check_payment'):
                            # Вызываем функцию
                            await check_payment_status(mock_update, mock_context)
                            
                            # Проверяем, что update_user_stats была вызвана с правильным user_id
                            mock_update_user_stats.assert_called_once_with(test_user_id)

@pytest.mark.asyncio
async def test_update_user_stats_is_called_in_auto_check_after_successful_payment():
    """Тест проверяет вызов update_user_stats в auto_check_payment_status после успешной оплаты."""
    # Создаем мок для контекста
    mock_context = MagicMock()
    mock_context.bot = MagicMock()
    mock_context.bot.edit_message_text = AsyncMock()
    mock_context.bot.delete_message = AsyncMock()
    mock_context.bot.send_message = AsyncMock()
    
    # Создаем данные платежа с тестовым user_id
    test_user_id = '456'
    user_data = {
        'payment': {
            'qrc_id': 'test_qrc_id',
            'user_id': test_user_id,
            'orders': ['1', '2'],
            'buttons_message_id': 789,
            'qr_message_id': 101,
            'status_checks': 0,
            'payment_id': '1'
        }
    }
    
    # Создаем мок для job
    job = MagicMock()
    job.data = {
        'chat_id': 123,
        'user_data': user_data
    }
    mock_context.job = job
    mock_context.job_queue = MagicMock()
    mock_context.job_queue.get_jobs_by_name = MagicMock(return_value=[MagicMock()])
    
    # Создаем мок для update_user_stats
    with patch('orderbot.services.user.update_user_stats') as mock_update_user_stats:
        # Настраиваем mock_update_user_stats.return_value
        mock_update_user_stats.return_value = True
        
        # Мокаем остальные внешние функции
        with patch('orderbot.services.sbp.get_qr_code_status', return_value={'status': 'accepted', 'message': 'Payment successful'}):
            with patch('orderbot.services.sheets.get_orders_sheet'):
                with patch('orderbot.services.sheets.get_payments_sheet'):
                    with patch('orderbot.handlers.payment.update_payment_status'):
                        # Вызываем функцию
                        await auto_check_payment_status(mock_context)
                        
                        # Проверяем, что update_user_stats была вызвана с правильным user_id
                        mock_update_user_stats.assert_called_once_with(test_user_id)

@pytest.mark.asyncio
async def test_update_user_stats_updates_user_data_properly():
    """Тест проверяет правильность обновления данных пользователя в функции update_user_stats."""
    from orderbot.services.user import update_user_stats
    
    # Тестовый ID пользователя
    test_user_id = '456'
    
    # Создаем моки для заказов и для пользовательских данных
    mock_orders = [
        ['id', 'date', 'status', 'user_id', 'username', 'sum'],  # Заголовок
        ['1', '01.01.2023 12:00:00', 'Оплачен', test_user_id, 'user1', '100'],  # Оплаченный заказ
        ['2', '02.01.2023 13:00:00', 'Принят', test_user_id, 'user1', '200'],   # Активный заказ
        ['3', '03.01.2023 14:00:00', 'Ожидает оплаты', test_user_id, 'user1', '300'], # Ожидает оплаты
        ['4', '04.01.2023 15:00:00', 'Отменён', test_user_id, 'user1', '400'],  # Отмененный заказ
        ['5', '05.01.2023 16:00:00', 'Оплачен', '789', 'user2', '500']  # Заказ другого пользователя
    ]
    
    mock_users = [
        ['user_id', 'profile', 'name', 'phone', 'room', 'orders', 'cancels', 'total', 'unpaid', 'start', 'last_order'],  # Заголовок
        [test_user_id, 't.me/user1', 'Test User', '123456789', '101', '1', '0', '0', '0', '01.01.2023 10:00:00', '']
    ]
    
    # Создаем патчи для внешних зависимостей
    with patch('orderbot.services.user.orders_sheet.get_all_values', return_value=mock_orders):
        with patch('orderbot.services.user.users_sheet.get_all_values', return_value=mock_users):
            with patch('orderbot.services.user.users_sheet.update') as mock_sheet_update:
                with patch('orderbot.services.user.users_sheet.update_cell') as mock_update_cell:
                    with patch('orderbot.services.user.logging.info') as mock_logging:
                        # Вызываем функцию
                        result = await update_user_stats(test_user_id)
                        
                        # Проверяем, что функция возвращает True
                        assert result is True
                        
                        # Проверяем, что была вызвана функция обновления ячеек с правильными параметрами
                        # Ожидаем, что update вызван со следующими параметрами:
                        # - строка: 2 (вторая строка в таблице)
                        # - диапазон: F2:I2 (столбцы F-I, строка 2)
                        # - значения: [['3', '1', '600', '500']] 
                        #   (3 активных заказа, 1 отмена, 600 общая сумма, 500 неоплаченная сумма)
                        mock_sheet_update.assert_called_once()
                        args, kwargs = mock_sheet_update.call_args
                        assert 'F2:I2' in args[0]  # Проверяем диапазон
                        assert len(args[1][0]) == 4  # Проверяем, что передано 4 значения
                        
                        # Проверяем правильные значения
                        values = args[1][0]
                        assert values[0] == '3'  # Активные заказы
                        assert values[1] == '1'  # Отмены
                        assert values[2] == '600'  # Общая сумма
                        assert values[3] == '500'  # Неоплаченная сумма
                        
                        # Проверяем, что была вызвана функция обновления даты последнего заказа
                        mock_update_cell.assert_called()
                        
                        # Проверяем логирование
                        mock_logging.assert_any_call(f"Обновлена статистика пользователей в таблице Users") 