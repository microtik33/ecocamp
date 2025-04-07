"""Тесты для модуля kitchen."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message
from telegram.ext import ContextTypes
from orderbot.handlers.kitchen import kitchen_summary

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

@pytest.fixture
def mock_orders_summary():
    """Создает мок данных сводки по заказам."""
    return {
        'date': '2024-04-07',
        'total_orders': 3,
        'breakfast': {
            'count': 1,
            'dishes': {'Каша': 1, 'Яичница': 1},
            'orders': ['Иван: Каша, Яичница']
        },
        'lunch': {
            'count': 1,
            'dishes': {'Суп': 1, 'Котлета': 1},
            'orders': ['Петр: Суп, Котлета']
        },
        'dinner': {
            'count': 1,
            'dishes': {'Рыба': 1, 'Салат': 1},
            'orders': ['Мария: Рыба, Салат']
        }
    }

@pytest.mark.asyncio
async def test_kitchen_summary_unauthorized(mock_update, mock_context):
    """Тест сводки по заказам для неавторизованного пользователя."""
    with patch('orderbot.handlers.kitchen.is_user_cook', return_value=False):
        await kitchen_summary(mock_update, mock_context)
        
        # Проверяем, что был вызван метод reply_text с сообщением об ошибке
        mock_update.message.reply_text.assert_called_once_with("У вас нет доступа к этой команде.")

@pytest.mark.asyncio
async def test_kitchen_summary_authorized(mock_update, mock_context, mock_orders_summary):
    """Тест сводки по заказам для авторизованного пользователя."""
    with patch('orderbot.handlers.kitchen.is_user_cook', return_value=True), \
         patch('orderbot.handlers.kitchen.get_orders_summary', return_value=mock_orders_summary):
        
        await kitchen_summary(mock_update, mock_context)
        
        # Проверяем, что метод reply_text был вызван 4 раза (общая информация + 3 приема пищи)
        assert mock_update.message.reply_text.call_count == 4
        
        # Проверяем содержимое сообщений
        calls = mock_update.message.reply_text.call_args_list
        
        # Проверяем общую информацию
        assert "Всего заказов: 3" in calls[0].args[0]
        
        # Проверяем завтрак
        assert "Завтрак" in calls[1].args[0]
        assert "Каша: 1" in calls[1].args[0]
        assert "Яичница: 1" in calls[1].args[0]
        
        # Проверяем обед
        assert "Обед" in calls[2].args[0]
        assert "Суп: 1" in calls[2].args[0]
        assert "Котлета: 1" in calls[2].args[0]
        
        # Проверяем ужин
        assert "Ужин" in calls[3].args[0]
        assert "Рыба: 1" in calls[3].args[0]
        assert "Салат: 1" in calls[3].args[0]

@pytest.mark.asyncio
async def test_kitchen_summary_no_orders(mock_update, mock_context):
    """Тест сводки по заказам при отсутствии заказов."""
    empty_summary = {
        'date': '2024-04-07',
        'total_orders': 0,
        'breakfast': {'count': 0, 'dishes': {}, 'orders': []},
        'lunch': {'count': 0, 'dishes': {}, 'orders': []},
        'dinner': {'count': 0, 'dishes': {}, 'orders': []}
    }
    
    with patch('orderbot.handlers.kitchen.is_user_cook', return_value=True), \
         patch('orderbot.handlers.kitchen.get_orders_summary', return_value=empty_summary):
        
        await kitchen_summary(mock_update, mock_context)
        
        # Проверяем, что метод reply_text был вызван 4 раза
        assert mock_update.message.reply_text.call_count == 4
        
        # Проверяем содержимое сообщений
        calls = mock_update.message.reply_text.call_args_list
        
        # Проверяем общую информацию
        assert "Всего заказов: 0" in calls[0].args[0]
        
        # Проверяем, что для каждого приема пищи показано "Нет заказов"
        for i in range(1, 4):
            assert "Нет заказов" in calls[i].args[0] 