"""Тесты для функционала sheets.py."""
from typing import TYPE_CHECKING
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch
    from _pytest.logging import LogCaptureFixture
    from pytest_mock import MockerFixture

# Создаем моки
mock_gspread = MagicMock()
mock_config = MagicMock()
mock_config.GOOGLE_CREDENTIALS_FILE = 'fake_credentials.json'
mock_config.ORDERS_SHEET_NAME = 'Orders'
mock_config.MENU_SHEET_NAME = 'Menu'

# Патчим модули
sys.modules['gspread'] = mock_gspread
sys.modules['config'] = mock_config

# Теперь импортируем наш модуль
from orderbot.services import sheets

# Фикстура для сброса состояния моков перед каждым тестом
@pytest.fixture(autouse=True)
def reset_mocks():
    """Сбрасывает состояние всех моков перед каждым тестом."""
    mock_gspread.reset_mock()
    mock_config.reset_mock()

# Фикстура для мока orders_sheet
@pytest.fixture
def mock_orders_sheet():
    """Создает мок для orders_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    mock.update.return_value = None
    mock.update_cell.return_value = None
    mock.find.return_value = None
    mock.append_row.return_value = None
    with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id', return_value=mock):
        yield mock

# Фикстура для мока users_sheet
@pytest.fixture
def mock_users_sheet():
    """Создает мок для users_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    mock.update.return_value = None
    with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id', return_value=mock):
        yield mock

@pytest.fixture
def mock_kitchen_sheet():
    """Создает мок для kitchen_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id', return_value=mock):
        yield mock

@pytest.fixture
def mock_rec_sheet():
    """Создает мок для rec_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    mock.update.return_value = None
    with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id', return_value=mock):
        yield mock

@pytest.fixture
def mock_auth_sheet():
    """Создает мок для auth_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id', return_value=mock):
        yield mock

@pytest.fixture
def mock_menu_sheet():
    """Создает мок для menu_sheet."""
    mock = MagicMock()
    mock.col_values.return_value = []
    with patch('orderbot.services.sheets.client.open.return_value.get_worksheet_by_id', return_value=mock):
        yield mock

@pytest.mark.asyncio
async def test_update_orders_status_batch_update(mock_orders_sheet: MagicMock):
    """Тест пакетного обновления статусов заказов."""
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Активный заказ на сегодня
        ['1', '2024-04-04', 'Активен', '1', '@user1', '100', '101', 'User1', 'breakfast', 'Блюдо1', '-', today_str],
        # Активный заказ на завтра
        ['2', '2024-04-04', 'Активен', '2', '@user2', '200', '102', 'User2', 'lunch', 'Блюдо2', '-', (today + timedelta(days=1)).strftime("%d.%m.%y")],
        # Активный заказ на сегодня
        ['3', '2024-04-04', 'Активен', '3', '@user3', '300', '103', 'User3', 'dinner', 'Блюдо3', '-', today_str],
        # Неактивный заказ на сегодня
        ['4', '2024-04-04', 'Отменён', '4', '@user4', '400', '104', 'User4', 'breakfast', 'Блюдо4', '-', today_str],
    ]
    
    # Настраиваем мок для get_all_values
    mock_orders_sheet.get_all_values.return_value = test_orders
    
    # Вызываем тестируемую функцию
    result = await sheets.update_orders_status()
    
    # Проверяем результат
    assert result is True
    
    # Проверяем, что были выполнены обновления только для активных заказов на сегодня
    expected_updates = [
        ('C2', [['Принят']]),  # Первый заказ
        ('C4', [['Принят']]),  # Третий заказ
    ]
    
    # Проверяем, что update был вызван с правильными параметрами
    assert mock_orders_sheet.update.call_count == len(expected_updates)
    for call, expected in zip(mock_orders_sheet.update.call_args_list, expected_updates):
        assert call[0][0] == expected[0]  # Проверяем диапазон
        assert call[0][1] == expected[1]  # Проверяем значения
        assert call[1]['value_input_option'] == 'USER_ENTERED'  # Проверяем опции

@pytest.mark.asyncio
async def test_update_orders_status_consecutive_rows(mock_orders_sheet: MagicMock):
    """Тест обновления статусов для последовательных строк."""
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы с последовательными строками
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Три последовательных активных заказа на сегодня
        ['1', '2024-04-04', 'Активен', '1', '@user1', '100', '101', 'User1', 'breakfast', 'Блюдо1', '-', today_str],
        ['2', '2024-04-04', 'Активен', '2', '@user2', '200', '102', 'User2', 'lunch', 'Блюдо2', '-', today_str],
        ['3', '2024-04-04', 'Активен', '3', '@user3', '300', '103', 'User3', 'dinner', 'Блюдо3', '-', today_str],
    ]
    
    # Настраиваем мок для get_all_values
    mock_orders_sheet.get_all_values.return_value = test_orders
    
    # Вызываем тестируемую функцию
    result = await sheets.update_orders_status()
    
    # Проверяем результат
    assert result is True
    
    # Проверяем, что было выполнено одно обновление для всех трех строк
    mock_orders_sheet.update.assert_called_once_with(
        'C2:C4',  # Диапазон из трех последовательных строк
        [['Принят'], ['Принят'], ['Принят']],  # Значения для каждой строки
        value_input_option='USER_ENTERED'
    )

def test_get_orders_sheet(mock_orders_sheet):
    """Тест получения листа заказов."""
    from orderbot.services.sheets import get_orders_sheet
    sheet = get_orders_sheet()
    assert sheet == mock_orders_sheet

def test_get_users_sheet(mock_users_sheet):
    """Тест получения листа пользователей."""
    from orderbot.services.sheets import get_users_sheet
    sheet = get_users_sheet()
    assert sheet == mock_users_sheet

def test_get_kitchen_sheet(mock_kitchen_sheet):
    """Тест получения листа кухни."""
    from orderbot.services.sheets import get_kitchen_sheet
    sheet = get_kitchen_sheet()
    assert sheet == mock_kitchen_sheet

def test_get_rec_sheet(mock_rec_sheet):
    """Тест получения листа рекомендаций."""
    from orderbot.services.sheets import get_rec_sheet
    sheet = get_rec_sheet()
    assert sheet == mock_rec_sheet

def test_get_auth_sheet(mock_auth_sheet):
    """Тест получения листа авторизации."""
    from orderbot.services.sheets import get_auth_sheet
    sheet = get_auth_sheet()
    assert sheet == mock_auth_sheet

def test_get_menu_sheet(mock_menu_sheet):
    """Тест получения листа меню."""
    from orderbot.services.sheets import get_menu_sheet
    sheet = get_menu_sheet()
    assert sheet == mock_menu_sheet 