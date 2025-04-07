"""Тесты для функционала создания, редактирования и отмены заказов."""
from datetime import datetime, timedelta, date
from typing import TYPE_CHECKING, Generator, Dict, Any

import pytest
from telegram import Update, User, Chat, Message, CallbackQuery
from telegram.constants import ChatType
from telegram.ext import CallbackContext, Application
from unittest.mock import MagicMock, AsyncMock
import sys
from pytest_mock import MockerFixture

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch

# Мокаем необходимые модули перед импортом order
mock_config = MagicMock()
mock_config.GOOGLE_CREDENTIALS_FILE = 'fake_credentials.json'
sys.modules['config'] = mock_config

# Создаем мок для orders_sheet
mock_orders_sheet = MagicMock()
mock_orders_sheet.get_all_values = MagicMock()
mock_orders_sheet.get_all_values.return_value = [
    ['ID', 'Timestamp', 'Status', 'UserID', 'Username', 'Total', 'Room', 'Name', 'MealType', 'Dishes', 'Wishes', 'DeliveryDate'],
    ['123', '2024-04-04 12:00:00', 'Активен', '1', '@test_user', '250', '101', 'Test User', 'breakfast', 'Блюдо 1', '-', '05.04.24']
]
mock_orders_sheet.update_cell = MagicMock()

mock_sheets = MagicMock()
mock_sheets.get_order = AsyncMock()
mock_sheets.save_order = AsyncMock()
mock_sheets.update_order = AsyncMock()
mock_sheets.get_next_order_id = MagicMock(return_value='123')
mock_sheets.orders_sheet = mock_orders_sheet
sys.modules['services.sheets'] = mock_sheets

mock_user = MagicMock()
mock_user.update_user_info = AsyncMock()
mock_user.update_user_stats = AsyncMock()
sys.modules['services.user'] = mock_user

mock_time_utils = MagicMock()
mock_time_utils.is_order_time.return_value = True
sys.modules['utils.time_utils'] = mock_time_utils

mock_auth = MagicMock()
mock_auth.is_user_authorized.return_value = True
sys.modules['services.auth'] = mock_auth

mock_translations = MagicMock()
mock_translations.get_meal_type = MagicMock(return_value='Завтрак')
mock_translations.get_button = MagicMock(return_value='Кнопка')
mock_translations.get_message = MagicMock(return_value='Сообщение')
sys.modules['translations'] = mock_translations

from orderbot.handlers import order

@pytest.fixture
def mock_update() -> Update:
    """Создает мок объекта Update."""
    # Создаем мок для бота
    bot = AsyncMock()
    bot.defaults = None
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    
    chat = Chat(id=1, type=ChatType.PRIVATE)
    user = User(id=1, is_bot=False, first_name='Test User')
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=user
    )
    message.set_bot(bot)  # Устанавливаем бота для сообщения
    
    # Создаем мок для CallbackQuery
    callback_query = MagicMock(spec=CallbackQuery)
    callback_query.id = '123'
    callback_query.from_user = user
    callback_query.chat_instance = '1'
    callback_query.data = 'test'
    callback_query.message = message
    callback_query.answer = AsyncMock()
    
    return Update(update_id=1, message=message, callback_query=callback_query)

@pytest.fixture
def mock_context() -> MagicMock:
    """Создает мок объекта CallbackContext."""
    context = MagicMock()
    context.user_data = {}
    
    # Создаем асинхронный мок для bot
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    context.bot = bot
    
    return context

@pytest.mark.asyncio
async def test_get_delivery_date() -> None:
    """Тест получения даты доставки."""
    today = date.today()
    delivery_date = order.get_delivery_date('breakfast')
    assert isinstance(delivery_date, date)
    assert delivery_date >= today

@pytest.mark.asyncio
async def test_process_order_save_success(
    mock_update: Update,
    mock_context: MagicMock,
) -> None:
    """Тест успешного сохранения заказа."""
    # Подготовка данных
    mock_context.user_data['order'] = {
        'room': '101',
        'name': 'Test User',
        'meal_type': 'breakfast',
        'dishes': ['Блюдо 1', 'Блюдо 2'],
        'quantities': {'Блюдо 1': 1, 'Блюдо 2': 2},
        'prices': {'Блюдо 1': 100, 'Блюдо 2': 150}  # Добавляем цены
    }

    # Настраиваем мок для save_order
    mock_sheets.save_order.return_value = True

    # Вызываем тестируемую функцию
    result = await order.process_order_save(mock_update, mock_context)

    # Проверяем результат
    assert result is not None
    mock_sheets.save_order.assert_called_once()
    assert mock_context.user_data['order']['order_id'] == "123"

@pytest.mark.asyncio
async def test_cancel_order_success(
    mock_update: Update,
    mock_context: MagicMock,
) -> None:
    """Тест успешной отмены заказа."""
    # Подготовка данных
    order_id = "123"
    mock_context.user_data['current_order_id'] = order_id
    mock_context.user_data['order'] = {  # Добавляем данные заказа
        'order_id': order_id,
        'room': '101',
        'name': 'Test User',
        'meal_type': 'breakfast',
        'dishes': ['Блюдо 1'],
        'status': 'Активен'
    }

    # Настраиваем мок для update_order
    mock_sheets.update_order.return_value = True

    # Вызываем тестируемую функцию
    result = await order.cancel_order(mock_update, mock_context)

    # Проверяем результат
    assert result is not None
    mock_orders_sheet.update_cell.assert_called_once_with(2, 3, 'Отменён')

@pytest.mark.asyncio
async def test_get_order_info_success(
    mock_update: Update,
    mock_context: MagicMock,
) -> None:
    """Тест получения информации о заказе."""
    # Подготовка данных
    order_id = "123"
    expected_order = {
        'order_id': order_id,
        'timestamp': '2024-04-04 12:00:00',
        'status': 'Активен',
        'user_id': '1',
        'username': '@test_user',
        'total_price': '250',
        'room': '101',
        'name': 'Test User',
        'meal_type': 'breakfast',
        'dishes': ['Блюдо 1'],
        'wishes': '-',
        'delivery_date': '05.04.24'
    }

    # Сбрасываем счетчик вызовов
    mock_orders_sheet.get_all_values.reset_mock()

    # Вызываем тестируемую функцию
    result = await order.get_order_info(order_id)

    # Проверяем результат
    assert result == expected_order
    mock_orders_sheet.get_all_values.assert_called_once()

@pytest.mark.asyncio
async def test_handle_order_update_success(
    mock_update: Update,
    mock_context: MagicMock,
) -> None:
    """Тест успешного обновления заказа."""
    # Подготовка данных
    order_id = "123"
    new_dishes = ["Новое блюдо 1", "Новое блюдо 2"]
    mock_context.user_data['current_order_id'] = order_id
    mock_context.user_data['order'] = {
        'order_id': order_id,
        'timestamp': '2024-04-04 12:00:00',
        'status': 'Активен',
        'user_id': '1',
        'username': '@test_user',
        'total_price': '250',
        'room': '101',
        'name': 'Test User',
        'meal_type': 'breakfast',
        'dishes': new_dishes,
        'quantities': {'Новое блюдо 1': 1, 'Новое блюдо 2': 1},
        'wishes': '-',
        'delivery_date': '05.04.24'
    }

    # Настраиваем мок для update_order
    mock_sheets.update_order.return_value = True
    
    # Устанавливаем корректное значение для callback_query.data
    mock_update.callback_query.data = 'edit_order'

    # Вызываем тестируемую функцию
    result = await order.handle_order_update(mock_update, mock_context)

    # Проверяем результат
    assert result is not None
    assert mock_context.user_data.get('editing') is True 