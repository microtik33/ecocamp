"""Тесты для функционала создания, редактирования и отмены заказов."""
from datetime import datetime, timedelta, date
from typing import TYPE_CHECKING, Generator, Dict, Any

import pytest
from telegram import Update, User, Chat, Message, CallbackQuery, InlineKeyboardMarkup
from telegram.constants import ChatType
from telegram.ext import CallbackContext, Application
from unittest.mock import MagicMock, AsyncMock, patch, ANY, call
import sys
from pytest_mock import MockerFixture
from orderbot.handlers.order import (
    MENU, ROOM, NAME, MEAL_TYPE, DISH_SELECTION, WISHES, QUESTION, EDIT_ORDER,
    get_delivery_date, show_order_form, handle_order_time_error, ask_room,
    ask_name, ask_meal_type, show_dishes, handle_dish_selection,
    handle_text_input, show_user_orders, handle_question, save_question,
    show_edit_active_orders, start_new_order, process_order_save
)

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch

from orderbot.handlers import order

@pytest.fixture
def mock_message() -> AsyncMock:
    """Создает мок объекта Message."""
    message = AsyncMock(spec=Message)
    message.message_id = 1
    message.chat_id = 1
    message.chat = Chat(id=1, type=ChatType.PRIVATE)
    message.from_user = User(id=1, is_bot=False, first_name='Test User')
    
    # Настраиваем возвращаемые значения
    sent_message = AsyncMock(spec=Message)
    sent_message.message_id = 2
    sent_message.chat_id = 1
    sent_message.chat = message.chat
    sent_message.from_user = message.from_user
    
    message.reply_text = AsyncMock(return_value=sent_message)
    message.edit_text = AsyncMock(return_value=sent_message)
    message.delete = AsyncMock()
    
    return message

@pytest.fixture
def mock_update(mock_message: AsyncMock) -> MagicMock:
    """Создает мок объекта Update."""
    # Создаем мок для бота
    bot = AsyncMock()
    bot.defaults = None
    
    # Настраиваем возвращаемые значения для методов бота
    sent_message = AsyncMock(spec=Message)
    sent_message.message_id = 2
    sent_message.chat_id = 1
    sent_message.chat = mock_message.chat
    sent_message.from_user = mock_message.from_user
    
    bot.send_message = AsyncMock(return_value=sent_message)
    bot.edit_message_text = AsyncMock(return_value=sent_message)
    bot.delete_message = AsyncMock()
    
    mock_message.bot = bot
    
    # Создаем мок для CallbackQuery
    callback_query = AsyncMock(spec=CallbackQuery)
    callback_query.id = '123'
    callback_query.from_user = mock_message.from_user
    callback_query.chat_instance = '1'
    callback_query.data = 'test'
    callback_query.message = mock_message
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock(return_value=sent_message)
    
    # Создаем объект Update с использованием MagicMock
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_message
    update.callback_query = callback_query
    update.effective_chat = mock_message.chat
    update.effective_user = mock_message.from_user
    
    return update

@pytest.fixture
def mock_context(mock_update: MagicMock) -> MagicMock:
    """Создает мок объекта Context."""
    context = MagicMock(spec=CallbackContext)
    context.user_data = {
        'order_chat_id': mock_update.effective_chat.id,
        'order_message_id': 1,
        'prompt_message_id': 1,
        'state': None
    }
    context.bot = mock_update.message.bot
    return context

@pytest.fixture(autouse=True)
def mock_translations():
    """Мокает модуль translations."""
    with patch('orderbot.translations.get_message') as mock_get_message, \
         patch('orderbot.translations.get_button') as mock_get_button:
        mock_get_message.side_effect = lambda key, **kwargs: {
            'enter_name': 'Введите ваше имя',
            'choose_meal': 'Выберите время приема пищи',
            'order_saved': 'Заказ сохранен',
            'question_saved': 'Спасибо за ваш вопрос',
            'no_active_orders': 'У вас нет активных заказов',
            'your_orders': 'Ваши активные заказы',
            'enter_question': 'Введите ваш вопрос',
            'question_thanks': 'Спасибо за ваш вопрос',
            'order_created': 'Заказ создан успешно',
            'order_updated': 'Заказ обновлен успешно',
            'order_time_error': 'Сейчас не время для заказов',
            'wrong_order_time': 'Сейчас не время для заказов',
            'choose_dishes': 'Выберите блюда'
        }.get(key, key)
        
        mock_get_button.side_effect = lambda key: {
            'back': 'Назад',
            'cancel': 'Отмена',
            'breakfast': 'Завтрак',
            'lunch': 'Обед',
            'dinner': 'Ужин',
            'done': 'Готово'
        }.get(key, key)
        yield

@pytest.fixture(autouse=True)
def mock_is_order_time():
    """Мокает функцию is_order_time."""
    with patch('orderbot.handlers.order.is_order_time', return_value=True):
        yield

@pytest.fixture(autouse=True)
def mock_sheets():
    """Мокает модуль sheets."""
    with patch('orderbot.services.sheets') as mock_sheets:
        mock_sheets.save_order = AsyncMock(return_value=True)
        mock_sheets.update_order = AsyncMock(return_value=True)
        mock_sheets.get_dishes_for_meal = MagicMock(return_value=[
            ('Каша', '100', '200 г'), 
            ('Яичница', '150', '150 г')
        ])
        mock_sheets.orders_sheet.get_all_values = AsyncMock(return_value=[
            ['ID', 'Статус', 'Комната', 'Имя', 'Тип', 'Блюда'],
            ['1', 'Активен', '101', 'Иван', 'breakfast', 'Каша']
        ])
        yield mock_sheets

@pytest.mark.asyncio
async def test_get_delivery_date() -> None:
    """Тест функции определения даты выдачи заказа."""
    result = get_delivery_date('breakfast')
    assert isinstance(result, date)
    assert result == (datetime.now().date() + timedelta(days=1))

@pytest.mark.asyncio
async def test_show_order_form_empty(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест показа пустой формы заказа."""
    result = await show_order_form(mock_update, mock_context)
    assert isinstance(result, str)
    assert "Ваш заказ" in result
    assert "—" in result

@pytest.mark.asyncio
async def test_show_order_form_with_data(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест показа формы заказа с данными."""
    mock_context.user_data['order'] = {
        'room': '101',
        'name': 'Иван',
        'meal_type': 'breakfast',
        'delivery_date': '01.04',
        'dishes': ['Каша', 'Яичница'],
        'quantities': {'Каша': 1, 'Яичница': 2}
    }
    result = await show_order_form(mock_update, mock_context)
    assert isinstance(result, str)
    assert "101" in result
    assert "Иван" in result
    assert "Каша x1" in result
    assert "Яичница x2" in result

@pytest.mark.asyncio
async def test_handle_order_time_error(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест обработки ошибки времени заказа."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = 'order_time_error'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Сейчас не время для заказов'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x):

        result = await handle_order_time_error(mock_update, mock_context)

        # Проверяем вызовы
        mock_update.callback_query.answer.assert_awaited_once()
        mock_update.callback_query.edit_message_text.assert_awaited_once_with(
            text='Сейчас не время для заказов',
            reply_markup=ANY
        )
        assert result == MENU

@pytest.mark.asyncio
async def test_ask_room(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест запроса номера комнаты."""
    mock_update.callback_query.data = "start:room"
    result = await ask_room(mock_update, mock_context)
    mock_update.callback_query.message.reply_text.assert_called()
    assert result == ROOM

@pytest.mark.asyncio
async def test_ask_name(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест запроса имени."""
    mock_context.user_data['order'] = {'room': '101'}
    mock_update.callback_query.data = "room:101"
    result = await ask_name(mock_update, mock_context)
    mock_update.callback_query.message.reply_text.assert_called()
    assert result == NAME

@pytest.mark.asyncio
async def test_ask_meal_type(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест запроса типа приема пищи."""
    mock_context.user_data['order'] = {'room': '101', 'name': 'Иван'}
    mock_context.user_data['order_chat_id'] = 1
    mock_context.user_data['order_message_id'] = 1
    mock_context.user_data['prompt_message_id'] = 1
    result = await ask_meal_type(mock_update, mock_context)
    mock_context.bot.edit_message_text.assert_called()
    assert result == MEAL_TYPE

@pytest.mark.asyncio
async def test_show_dishes(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест отображения блюд."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = 'meal:breakfast'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1
    
    # Настраиваем мок для message
    mock_update.callback_query.message = AsyncMock()
    mock_update.callback_query.message.reply_text = AsyncMock(return_value=AsyncMock())
    mock_update.callback_query.message.delete = AsyncMock()

    # Настраиваем данные пользователя
    mock_context.user_data = {
        'order': {
            'room': '101',
            'name': 'Иван',
            'meal_type': 'breakfast'
        },
        'order_chat_id': 1,
        'order_message_id': 1
    }

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Выберите блюда'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x), \
         patch('orderbot.handlers.order.is_order_time', return_value=True), \
         patch('orderbot.handlers.order.is_user_authorized', return_value=True):

        result = await show_dishes(mock_update, mock_context)
        
        # Проверяем вызовы
        mock_update.callback_query.answer.assert_awaited_once()
        mock_update.callback_query.message.reply_text.assert_awaited_once_with(
            'Выберите блюда',
            reply_markup=ANY
        )
        
        # Проверяем клавиатуру
        call_args = mock_update.callback_query.message.reply_text.call_args
        assert call_args is not None
        keyboard = call_args[1]['reply_markup']
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) > 0
        
        assert result == DISH_SELECTION

@pytest.mark.asyncio
async def test_handle_dish_selection(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест обработки выбора блюд."""
    mock_context.user_data['order'] = {
        'room': '101',
        'name': 'Иван',
        'meal_type': 'breakfast',
        'dishes': [],
        'quantities': {}
    }
    mock_update.callback_query.data = 'select_dish:Каша'
    
    result = await handle_dish_selection(mock_update, mock_context)
    
    assert 'Каша' in mock_context.user_data['order']['dishes']
    assert mock_context.user_data['order']['quantities']['Каша'] == 1
    assert result == DISH_SELECTION

@pytest.mark.asyncio
async def test_handle_text_input(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест обработки текстового ввода."""
    mock_context.user_data['order'] = {'room': '101'}
    mock_context.user_data['state'] = NAME
    mock_update.message.text = 'Иван'
    result = await handle_text_input(mock_update, mock_context)
    assert mock_context.user_data['order']['name'] == 'Иван'
    assert result == MEAL_TYPE

@pytest.mark.asyncio
async def test_show_user_orders(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест показа заказов пользователя."""
    # Настраиваем мок для заказов
    mock_orders = [
        ['ID', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата'],
        ['1', '2024-03-14', 'Активен', '1', '@test', '100', '101', 'Test User', 'breakfast', 'Каша', '-', '2024-03-15']
    ]
    
    with patch('orderbot.services.sheets.get_orders_sheet') as mock_get_sheet:
        mock_sheet = MagicMock()
        mock_sheet.get_all_values.return_value = mock_orders
        mock_get_sheet.return_value = mock_sheet
        
        # Настраиваем мок для translations
        with patch('orderbot.translations.get_message') as mock_get_message:
            mock_get_message.side_effect = lambda key, **kwargs: {
                'active_orders_separator': '\n---\n',
                'total_sum': 'Общая сумма: {sum} р.',
                'what_next': 'Что дальше?'
            }.get(key, 'Ваши активные заказы:')
            
            with patch('orderbot.translations.get_meal_type', return_value='Завтрак'):
                result = await show_user_orders(mock_update, mock_context)
                
                # Проверяем вызовы
                mock_update.message.reply_text.assert_called()
                args = mock_update.message.reply_text.call_args
                assert args is not None
                assert "Ваши активные заказы:" in args[0][0]
                assert result == MENU

@pytest.mark.asyncio
async def test_handle_question(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест обработки вопроса пользователя."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = 'ask_question'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Задайте ваш вопрос'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x):

        result = await handle_question(mock_update, mock_context)

        # Проверяем вызовы
        mock_update.callback_query.answer.assert_awaited_once()
        mock_update.callback_query.edit_message_text.assert_awaited_once_with(
            text='Задайте ваш вопрос',
            reply_markup=ANY
        )
        assert result == QUESTION

@pytest.mark.asyncio
async def test_save_question(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест сохранения вопроса."""
    mock_update.message.text = "Какой у вас график работы?"
    result = await save_question(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once()
    args = mock_update.message.reply_text.call_args
    assert args is not None
    assert "Спасибо за ваш вопрос" in args[0][0]
    assert result == MENU

@pytest.mark.asyncio
async def test_show_edit_active_orders(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест отображения формы редактирования активных заказов."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = 'edit_orders'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Выберите заказ для редактирования'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x):

        result = await show_edit_active_orders(mock_update, mock_context)
        
        # Проверяем вызовы
        mock_update.callback_query.answer.assert_awaited_once()
        mock_update.callback_query.edit_message_text.assert_awaited_once()

@pytest.mark.asyncio
async def test_start_new_order(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест начала нового заказа."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    mock_update.callback_query.data = 'new_order'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1
    
    # Настраиваем мок для message
    mock_update.message = AsyncMock()
    mock_update.message.reply_text = AsyncMock(return_value=AsyncMock())
    mock_update.effective_user = MagicMock()
    mock_update.effective_user.id = 1

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', side_effect=lambda x: 'Выберите комнату' if x == 'choose_room' else ''), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x), \
         patch('orderbot.handlers.order.is_order_time', return_value=True), \
         patch('orderbot.handlers.order.is_user_authorized', return_value=True):

        result = await start_new_order(mock_update, mock_context)
        
        # Проверяем вызовы
        assert mock_update.message.reply_text.call_count >= 2
        
        # Проверяем последний вызов (должен быть для выбора комнаты)
        last_call = mock_update.message.reply_text.call_args_list[-1]
        assert last_call[0][0] == 'Выберите комнату'
        assert 'reply_markup' in last_call[1]
        
        # Проверяем клавиатуру
        keyboard = last_call[1]['reply_markup']
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) > 0
        
        assert result == ROOM

@pytest.mark.asyncio
async def test_process_order_save_success(mock_update: Update, mock_context: MagicMock) -> None:
    """Тест успешного сохранения заказа."""
    # Настраиваем мок для callback_query
    mock_update.callback_query = AsyncMock()
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock(return_value=AsyncMock())
    mock_update.callback_query.data = 'save_order'
    mock_update.callback_query.from_user = MagicMock()
    mock_update.callback_query.from_user.id = 1
    
    # Настраиваем мок для message и effective_chat
    mock_update.effective_chat = MagicMock()
    mock_update.effective_chat.id = 1
    mock_update.effective_user = MagicMock()
    mock_update.effective_user.id = 1
    mock_update.effective_user.username = 'test_user'

    # Настраиваем мок для sheets
    mock_sheets = AsyncMock()
    mock_sheets.save_order = AsyncMock(return_value=True)
    mock_context.bot_data = {'sheets': mock_sheets}
    mock_context.bot = AsyncMock()
    mock_context.bot.send_message = AsyncMock(return_value=AsyncMock())
    mock_context.bot.delete_message = AsyncMock()

    # Добавляем данные заказа
    mock_context.user_data = {
        'order': {
            'room': '101',
            'name': 'Test User',
            'meal_type': 'breakfast',
            'dishes': ['Блюдо 1', 'Блюдо 2'],
            'quantities': {'Блюдо 1': 1, 'Блюдо 2': 2},
            'prices': {'Блюдо 1': 100, 'Блюдо 2': 150}
        },
        'order_chat_id': 123,
        'order_message_id': 456
    }

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Заказ успешно сохранен'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x), \
         patch('orderbot.services.sheets.save_order', return_value=True), \
         patch('orderbot.services.sheets.get_next_order_id', return_value='123'), \
         patch('orderbot.translations.get_meal_type', return_value='Завтрак'):

        result = await process_order_save(mock_update, mock_context)
        
        # Проверяем вызовы
        mock_update.callback_query.edit_message_text.assert_awaited_once()
        
        # Проверяем содержимое сообщения
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert call_args is not None
        assert isinstance(call_args[1]['reply_markup'], InlineKeyboardMarkup)
        assert len(call_args[1]['reply_markup'].inline_keyboard) > 0
        
        assert result == MENU

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
    update.callback_query = mocker.AsyncMock(spec=CallbackQuery)
    update.callback_query.answer = mocker.AsyncMock()
    update.callback_query.edit_message_text = mocker.AsyncMock()
    update.callback_query.data = 'cancel_123'
    update.callback_query.from_user = mocker.MagicMock(spec=User)
    update.callback_query.from_user.id = '1'

    # Создаем мок для context
    context = mocker.MagicMock()
    context.user_data = {'order': order_data}

    # Настраиваем мок для translations
    with patch('orderbot.translations.get_message', return_value='Заказ успешно отменён'), \
         patch('orderbot.translations.get_button', side_effect=lambda x: x), \
         patch('orderbot.services.sheets.get_order', return_value=order_data), \
         patch('orderbot.services.sheets.update_order', return_value=True), \
         patch('orderbot.handlers.order.update_user_stats', return_value=None), \
         patch('orderbot.handlers.order.is_order_time', return_value=True):

        # Вызываем тестируемую функцию
        from orderbot.handlers.order import cancel_order
        result = await cancel_order(update, context)

        # Проверяем вызовы
        update.callback_query.answer.assert_awaited_once()
        update.callback_query.edit_message_text.assert_awaited_once()

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

    # Настраиваем мок для sheets.orders_sheet
    mock_sheet = MagicMock()
    mock_sheet.get_all_values = MagicMock(return_value=[
        ['ID', 'Timestamp', 'Status', 'UserID', 'Username', 'Total', 'Room', 'Name', 'MealType', 'Dishes', 'Wishes', 'DeliveryDate'],
        ['123', '2024-04-04 12:00:00', 'Активен', '1', '@test_user', '250', '101', 'Test User', 'breakfast', 'Блюдо 1', '-', '05.04.24']
    ])

    with patch('orderbot.services.sheets.get_orders_sheet', return_value=mock_sheet):
        # Вызываем тестируемую функцию
        from orderbot.handlers.order import get_order_info
        result = await get_order_info(order_id)

        # Проверяем результат
        assert result is not None
        assert result['order_id'] == expected_order['order_id']
        assert result['status'] == expected_order['status']
        assert result['user_id'] == expected_order['user_id']
        assert result['room'] == expected_order['room']
        assert result['name'] == expected_order['name']
        assert result['meal_type'] == expected_order['meal_type']
        assert result['dishes'] == expected_order['dishes']
        assert result['wishes'] == expected_order['wishes']
        assert result['delivery_date'] == expected_order['delivery_date']
        
        # Проверяем вызов get_all_values
        mock_sheet.get_all_values.assert_called_once()

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