"""Тесты для модуля menu."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message
from telegram.ext import ContextTypes
from orderbot.handlers.menu import start, MENU

@pytest.fixture
def mock_update():
    """Создает мок объекта Update."""
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = "123456789"
    update.message = MagicMock(spec=Message)
    return update

@pytest.fixture
def mock_context():
    """Создает мок объекта Context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {}
    return context

@pytest.mark.asyncio
async def test_start_during_order_time(mock_update, mock_context):
    """Тест начала работы в разрешенное для заказов время."""
    with patch('orderbot.handlers.menu.is_order_time', return_value=True), \
         patch('orderbot.handlers.menu.update_user_info', new_callable=AsyncMock):
        
        result = await start(mock_update, mock_context)
        
        # Проверяем, что user_data был очищен
        assert not mock_context.user_data
        
        # Проверяем, что был вызван метод reply_text
        mock_update.message.reply_text.assert_called_once()
        
        # Проверяем, что возвращено состояние MENU
        assert result == MENU
        
        # Проверяем, что кнопка заказа активна
        call_args = mock_update.message.reply_text.call_args
        reply_markup = call_args.kwargs['reply_markup']
        assert 'new_order' in reply_markup.inline_keyboard[0][0].callback_data
        assert '⛔' not in reply_markup.inline_keyboard[0][0].text

@pytest.mark.asyncio
async def test_start_outside_order_time(mock_update, mock_context):
    """Тест начала работы в запрещенное для заказов время."""
    with patch('orderbot.handlers.menu.is_order_time', return_value=False), \
         patch('orderbot.handlers.menu.update_user_info', new_callable=AsyncMock):
        
        result = await start(mock_update, mock_context)
        
        # Проверяем, что user_data был очищен
        assert not mock_context.user_data
        
        # Проверяем, что был вызван метод reply_text
        mock_update.message.reply_text.assert_called_once()
        
        # Проверяем, что возвращено состояние MENU
        assert result == MENU
        
        # Проверяем, что кнопка заказа неактивна
        call_args = mock_update.message.reply_text.call_args
        reply_markup = call_args.kwargs['reply_markup']
        assert 'order_time_error' in reply_markup.inline_keyboard[0][0].callback_data
        assert '⛔' in reply_markup.inline_keyboard[0][0].text

@pytest.mark.asyncio
async def test_start_clears_user_data(mock_update, mock_context):
    """Тест очистки user_data при начале работы."""
    # Добавляем данные в user_data
    mock_context.user_data['test_key'] = 'test_value'
    
    with patch('orderbot.handlers.menu.is_order_time', return_value=True), \
         patch('orderbot.handlers.menu.update_user_info', new_callable=AsyncMock):
        
        await start(mock_update, mock_context)
        
        # Проверяем, что user_data был очищен
        assert not mock_context.user_data 