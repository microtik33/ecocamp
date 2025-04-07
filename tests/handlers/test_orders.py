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
from orderbot.handlers.order import MENU

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch

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
    from orderbot.services import sheets
    sheets.save_order.return_value = True

    # Вызываем тестируемую функцию
    result = await order.process_order_save(mock_update, mock_context)

    # Проверяем результат
    assert result is not None
    sheets.save_order.assert_called_once()
    assert mock_context.user_data['order']['order_id'] == "123"

@pytest.mark.asyncio
async def test_cancel_order_success(mocker: MockerFixture) -> None:
    """Тест успешной отмены заказа."""
    # Подготавливаем данные заказа
    order_data = {
        'order_id': '123',
        'status': 'Активен',
        'user_id': '1',
        'order_chat_id': '100'
    }

    # Создаем мок для Update
    update = mocker.MagicMock(spec=Update)

    # Создаем мок для User
    user = mocker.MagicMock(spec=User)
    user.id = '1'

    # Создаем мок для Message
    message = mocker.AsyncMock(spec=Message)
    message.chat.id = '100'

    # Создаем мок для CallbackQuery
    callback_query = mocker.AsyncMock(spec=CallbackQuery)
    callback_query.from_user = user
    callback_query.data = 'cancel_123'
    callback_query.message = message
    callback_query.answer = mocker.AsyncMock()
    callback_query.edit_message_text = mocker.AsyncMock()

    # Устанавливаем callback_query в update
    update.callback_query = callback_query

    # Создаем мок для context
    context = mocker.MagicMock()
    context.user_data = {'order': order_data}

    # Мокаем sheets.get_order
    mocker.patch('orderbot.services.sheets.get_order', return_value=order_data)

    # Мокаем translations
    mocker.patch('orderbot.translations.get_message', return_value='Заказ успешно отменён')
    mocker.patch('orderbot.translations.get_button', side_effect=lambda x: x)

    # Мокаем update_user_stats
    mocker.patch('orderbot.handlers.order.update_user_stats', return_value=None)

    # Вызываем тестируемую функцию
    from orderbot.handlers.order import cancel_order
    result = await cancel_order(update, context)

    # Проверяем, что методы были вызваны
    callback_query.answer.assert_awaited_once()
    callback_query.edit_message_text.assert_awaited_once()
    assert result == MENU
    assert not context.user_data

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
    from orderbot.services import sheets
    sheets.orders_sheet.get_all_values.reset_mock()
    sheets.orders_sheet.get_all_values.return_value = [
        ['ID', 'Timestamp', 'Status', 'UserID', 'Username', 'Total', 'Room', 'Name', 'MealType', 'Dishes', 'Wishes', 'DeliveryDate'],
        ['123', '2024-04-04 12:00:00', 'Активен', '1', '@test_user', '250', '101', 'Test User', 'breakfast', 'Блюдо 1', '-', '05.04.24']
    ]

    # Вызываем тестируемую функцию
    result = await order.get_order_info(order_id)

    # Проверяем результат
    assert result == expected_order
    sheets.orders_sheet.get_all_values.assert_called_once()

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
    from orderbot.services import sheets
    sheets.update_order.return_value = True
    
    # Устанавливаем корректное значение для callback_query.data
    mock_update.callback_query.data = 'edit_order'

    # Вызываем тестируемую функцию
    result = await order.handle_order_update(mock_update, mock_context)

    # Проверяем результат
    assert result is not None
    assert mock_context.user_data.get('editing') is True 