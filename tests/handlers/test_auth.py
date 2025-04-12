"""Тесты для модуля auth."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, Contact
from telegram.ext import ContextTypes
from orderbot.handlers.auth import start, handle_phone
from orderbot.handlers.states import MENU, PHONE
from orderbot.services.sheets import is_user_authorized, check_phone, save_user_id
from orderbot.services.user import update_user_info
from orderbot.utils.auth_decorator import require_auth

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
    return context

@pytest.mark.asyncio
async def test_start_authorized_user(mock_update, mock_context):
    """Тест начала работы с авторизованным пользователем."""
    with patch('orderbot.handlers.auth.is_user_authorized', return_value=True), \
         patch('orderbot.handlers.auth.update_user_info', new_callable=AsyncMock):
        
        result = await start(mock_update, mock_context)
        
        # Проверяем, что был вызван метод reply_text
        mock_update.message.reply_text.assert_called_once()
        # Проверяем, что возвращено состояние MENU
        assert result == MENU

@pytest.mark.asyncio
async def test_start_unauthorized_user(mock_update, mock_context):
    """Тест начала работы с неавторизованным пользователем."""
    with patch('orderbot.handlers.auth.is_user_authorized', return_value=False), \
         patch('orderbot.handlers.auth.update_user_info', new_callable=AsyncMock):
        
        result = await start(mock_update, mock_context)
        
        # Проверяем, что был вызван метод reply_text
        mock_update.message.reply_text.assert_called_once()
        # Проверяем, что возвращено состояние PHONE
        assert result == PHONE

@pytest.mark.asyncio
async def test_handle_phone_valid(mock_update, mock_context):
    """Тест обработки валидного номера телефона."""
    # Создаем мок для контакта
    contact = MagicMock(spec=Contact)
    contact.phone_number = "79123456789"
    mock_update.message.contact = contact
    
    with patch('orderbot.handlers.auth.check_phone', return_value=True), \
         patch('orderbot.handlers.auth.save_user_id', return_value=True), \
         patch('orderbot.handlers.auth.update_user_info', new_callable=AsyncMock):
        
        result = await handle_phone(mock_update, mock_context)
        
        # Проверяем, что были вызваны методы reply_text
        assert mock_update.message.reply_text.call_count == 2
        # Проверяем, что возвращено состояние MENU
        assert result == MENU

@pytest.mark.asyncio
async def test_handle_phone_invalid(mock_update, mock_context):
    """Тест обработки невалидного номера телефона."""
    # Создаем мок для контакта
    contact = MagicMock(spec=Contact)
    contact.phone_number = "79123456789"
    mock_update.message.contact = contact
    
    with patch('orderbot.handlers.auth.check_phone', return_value=False), \
         patch('orderbot.handlers.auth.update_user_info', new_callable=AsyncMock):
        
        result = await handle_phone(mock_update, mock_context)
        
        # Проверяем, что был вызван метод reply_text
        mock_update.message.reply_text.assert_called_once()
        # Проверяем, что возвращено состояние PHONE
        assert result == PHONE

@pytest.mark.asyncio
async def test_handle_phone_no_contact(mock_update, mock_context):
    """Тест обработки отсутствующего контакта."""
    mock_update.message.contact = None
    
    result = await handle_phone(mock_update, mock_context)
    
    # Проверяем, что был вызван метод reply_text
    mock_update.message.reply_text.assert_called_once()
    # Проверяем, что возвращено состояние PHONE
    assert result == PHONE

@pytest.mark.asyncio
async def test_require_auth_authorized_user(mock_update, mock_context):
    """Тест декоратора require_auth для авторизованного пользователя."""
    async def test_func(update, context):
        return "success"
    
    decorated_func = require_auth(test_func)
    
    with patch('orderbot.utils.auth_decorator.is_user_authorized', return_value=True):
        result = await decorated_func(mock_update, mock_context)
        assert result == "success"

@pytest.mark.asyncio
async def test_require_auth_unauthorized_user(mock_update, mock_context):
    """Тест декоратора require_auth для неавторизованного пользователя."""
    async def test_func(update, context):
        return "success"
    
    decorated_func = require_auth(test_func)
    
    with patch('orderbot.utils.auth_decorator.is_user_authorized', return_value=False):
        result = await decorated_func(mock_update, mock_context)
        assert result == PHONE
        mock_update.message.reply_text.assert_called_once() 