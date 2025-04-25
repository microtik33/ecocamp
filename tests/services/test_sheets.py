"""Тесты для функционала sheets.py."""
# ВАЖНО: Для тестирования функций, которые используют get_orders_sheet() и другие геттеры,
# необходимо правильно патчить эти функции. Используйте следующий подход:
#
# 1. Создайте мок: mock_sheet = MagicMock()
# 2. Сохраните оригинальную функцию: original_get_orders_sheet = sheets.get_orders_sheet
# 3. Замените ее на мок: sheets.get_orders_sheet = lambda: mock_sheet
# 4. Восстановите оригинальную функцию в блоке finally: sheets.get_orders_sheet = original_get_orders_sheet
#
# Примеры правильной реализации смотрите в тестах:
# - test_check_orders_awaiting_payment_at_startup()
# - test_update_orders_to_awaiting_payment_breakfast()

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
mock_config.ORDERS_SHEET_ID = 'orders_sheet_id'
mock_config.MENU_SHEET_ID = 'menu_sheet_id'

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
    
    # Патчим функцию get_orders_sheet, чтобы она возвращала наш мок
    with patch('orderbot.services.sheets.get_orders_sheet', return_value=mock):
        yield mock

# Фикстура для мока users_sheet
@pytest.fixture
def mock_users_sheet():
    """Создает мок для users_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    mock.update.return_value = None
    
    # Патчим функцию get_users_sheet
    with patch('orderbot.services.sheets.get_users_sheet', return_value=mock):
        yield mock

@pytest.fixture
def mock_kitchen_sheet():
    """Создает мок для kitchen_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    
    # Патчим функцию get_kitchen_sheet
    with patch('orderbot.services.sheets.get_kitchen_sheet', return_value=mock):
        yield mock

@pytest.fixture
def mock_rec_sheet():
    """Создает мок для rec_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    mock.update.return_value = None
    
    # Патчим функцию get_rec_sheet
    with patch('orderbot.services.sheets.get_rec_sheet', return_value=mock):
        yield mock

@pytest.fixture
def mock_auth_sheet():
    """Создает мок для auth_sheet."""
    mock = MagicMock()
    mock.get_all_values.return_value = []
    
    # Патчим функцию get_auth_sheet
    with patch('orderbot.services.sheets.get_auth_sheet', return_value=mock):
        yield mock

@pytest.fixture
def mock_menu_sheet():
    """Создает мок для menu_sheet."""
    mock = MagicMock()
    mock.col_values.return_value = []
    
    # Патчим функцию get_menu_sheet
    with patch('orderbot.services.sheets.get_menu_sheet', return_value=mock):
        yield mock

@pytest.mark.asyncio
async def test_update_orders_status_batch_update():
    """Тест пакетного обновления статусов заказов."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
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
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
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
        assert mock_sheet.update.call_count == len(expected_updates)
        for call, expected in zip(mock_sheet.update.call_args_list, expected_updates):
            assert call[0][0] == expected[0]  # Проверяем диапазон
            assert call[0][1] == expected[1]  # Проверяем значения
            assert call[1]['value_input_option'] == 'USER_ENTERED'  # Проверяем опции
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_status_consecutive_rows():
    """Тест обновления статусов для последовательных строк."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
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
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
        # Вызываем тестируемую функцию
        result = await sheets.update_orders_status()
        
        # Проверяем результат
        assert result is True
        
        # Проверяем, что было выполнено одно обновление для всех трех строк
        mock_sheet.update.assert_called_once_with(
            'C2:C4',  # Диапазон из трех последовательных строк
            [['Принят'], ['Принят'], ['Принят']],  # Значения для каждой строки
            value_input_option='USER_ENTERED'
        )
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_to_awaiting_payment_breakfast():
    """Тест обновления статусов заказов на 'Ожидает оплаты' для завтрака в 9:00."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказ завтрака на сегодня со статусом Принят
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        # Заказ обеда на сегодня со статусом Принят
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Обед', 'Блюдо2', '-', today_str],
        # Заказ ужина на сегодня со статусом Принят
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Ужин', 'Блюдо3', '-', today_str],
        # Заказ завтрака на сегодня со статусом Активен (не должен измениться)
        ['4', '2024-04-04', 'Активен', '4', '@user4', '400', '104', 'User4', 'Завтрак', 'Блюдо4', '-', today_str],
        # Заказ завтрака на завтра (не должен измениться)
        ['5', '2024-04-04', 'Принят', '5', '@user5', '500', '105', 'User5', 'Завтрак', 'Блюдо5', '-', (today + timedelta(days=1)).strftime("%d.%m.%y")],
    ]
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
        # Устанавливаем текущее время на 9:00
        with patch('orderbot.services.sheets.datetime') as mock_dt:
            # Фиксируем дату и время
            fixed_date = datetime.now().date()
            test_time = datetime.combine(fixed_date, datetime.min.time().replace(hour=9))
            
            # Настраиваем мок datetime
            mock_dt.now.return_value = test_time
            mock_dt.strptime = datetime.strptime
            mock_dt.combine = datetime.combine
            
            # Вызываем тестируемую функцию
            result = await sheets.update_orders_to_awaiting_payment()
            
            # Проверяем результат
            assert result is True
            
            # Проверяем, что был выполнен только один вызов update для заказа завтрака на сегодня
            mock_sheet.update.assert_called_once_with(
                'C2',  # Только строка с завтраком
                [['Ожидает оплаты']],  # Новый статус
                value_input_option='USER_ENTERED'
            )
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_to_awaiting_payment_lunch():
    """Тест обновления статусов заказов на 'Ожидает оплаты' для обеда в 14:00."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказ завтрака на сегодня со статусом Принят
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        # Заказ обеда на сегодня со статусом Принят
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Обед', 'Блюдо2', '-', today_str],
        # Заказ ужина на сегодня со статусом Принят
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Ужин', 'Блюдо3', '-', today_str],
        # Заказ обеда на сегодня со статусом Активен (не должен измениться)
        ['4', '2024-04-04', 'Активен', '4', '@user4', '400', '104', 'User4', 'Обед', 'Блюдо4', '-', today_str],
        # Заказ обеда на завтра (не должен измениться)
        ['5', '2024-04-04', 'Принят', '5', '@user5', '500', '105', 'User5', 'Обед', 'Блюдо5', '-', (today + timedelta(days=1)).strftime("%d.%m.%y")],
    ]
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
        # Устанавливаем текущее время на 14:00
        with patch('orderbot.services.sheets.datetime') as mock_dt:
            # Фиксируем дату и время
            fixed_date = datetime.now().date()
            test_time = datetime.combine(fixed_date, datetime.min.time().replace(hour=14))
            
            # Настраиваем мок datetime
            mock_dt.now.return_value = test_time
            mock_dt.strptime = datetime.strptime
            mock_dt.combine = datetime.combine
            
            # Вызываем тестируемую функцию
            result = await sheets.update_orders_to_awaiting_payment()
            
            # Проверяем результат
            assert result is True
            
            # Проверяем, что был выполнен только один вызов update для заказа обеда на сегодня
            mock_sheet.update.assert_called_once_with(
                'C3',  # Только строка с обедом
                [['Ожидает оплаты']],  # Новый статус
                value_input_option='USER_ENTERED'
            )
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_to_awaiting_payment_dinner():
    """Тест обновления статусов заказов на 'Ожидает оплаты' для ужина в 19:00."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказ завтрака на сегодня со статусом Принят
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        # Заказ обеда на сегодня со статусом Принят
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Обед', 'Блюдо2', '-', today_str],
        # Заказ ужина на сегодня со статусом Принят
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Ужин', 'Блюдо3', '-', today_str],
        # Заказ ужина на сегодня со статусом Активен (не должен измениться)
        ['4', '2024-04-04', 'Активен', '4', '@user4', '400', '104', 'User4', 'Ужин', 'Блюдо4', '-', today_str],
        # Заказ ужина на завтра (не должен измениться)
        ['5', '2024-04-04', 'Принят', '5', '@user5', '500', '105', 'User5', 'Ужин', 'Блюдо5', '-', (today + timedelta(days=1)).strftime("%d.%m.%y")],
    ]
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
        # Устанавливаем текущее время на 19:00
        with patch('orderbot.services.sheets.datetime') as mock_dt:
            # Фиксируем дату и время
            fixed_date = datetime.now().date()
            test_time = datetime.combine(fixed_date, datetime.min.time().replace(hour=19))
            
            # Настраиваем мок datetime
            mock_dt.now.return_value = test_time
            mock_dt.strptime = datetime.strptime
            mock_dt.combine = datetime.combine
            
            # Вызываем тестируемую функцию
            result = await sheets.update_orders_to_awaiting_payment()
            
            # Проверяем результат
            assert result is True
            
            # Проверяем, что был выполнен только один вызов update для заказа ужина на сегодня
            mock_sheet.update.assert_called_once_with(
                'C4',  # Только строка с ужином
                [['Ожидает оплаты']],  # Новый статус
                value_input_option='USER_ENTERED'
            )
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_to_awaiting_payment_wrong_time(mock_orders_sheet: MagicMock):
    """Тест, что функция не обновляет статусы заказов в неположенное время."""
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказы на сегодня со статусом Принят
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Обед', 'Блюдо2', '-', today_str],
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Ужин', 'Блюдо3', '-', today_str],
    ]
    
    # Настраиваем мок для get_all_values
    mock_orders_sheet.get_all_values.return_value = test_orders
    
    # Устанавливаем текущее время на 12:00 (не соответствует времени обновления)
    with patch('orderbot.services.sheets.datetime') as mock_dt:
        mock_dt.now.return_value = datetime.combine(today, datetime.min.time().replace(hour=12))
        
        # Вызываем тестируемую функцию
        result = await sheets.update_orders_to_awaiting_payment()
        
        # Проверяем результат
        assert result is True
        
        # Проверяем, что update не был вызван
        mock_orders_sheet.update.assert_not_called()

@pytest.mark.asyncio
async def test_update_orders_to_awaiting_payment_multiple_orders(mock_orders_sheet: MagicMock):
    """Тест обновления статусов для нескольких заказов одного типа одновременно."""
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Несколько заказов завтрака на сегодня со статусом Принят
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Завтрак', 'Блюдо2', '-', today_str],
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Завтрак', 'Блюдо3', '-', today_str],
        # Заказ другого типа
        ['4', '2024-04-04', 'Принят', '4', '@user4', '400', '104', 'User4', 'Обед', 'Блюдо4', '-', today_str],
    ]
    
    # Настраиваем мок для get_all_values
    mock_orders_sheet.get_all_values.return_value = test_orders
    
    # Устанавливаем текущее время на 9:00
    with patch('orderbot.services.sheets.datetime') as mock_dt:
        mock_dt.now.return_value = datetime.combine(today, datetime.min.time().replace(hour=9))
        mock_dt.strptime.side_effect = lambda *args, **kw: datetime.strptime(*args, **kw)
        
        # Вызываем тестируемую функцию
        result = await sheets.update_orders_to_awaiting_payment()
        
        # Проверяем результат
        assert result is True
        
        # Проверяем, что был выполнен один вызов update для всех трех заказов завтрака
        mock_orders_sheet.update.assert_called_once_with(
            'C2:C4',  # Диапазон для трех последовательных заказов завтрака
            [['Ожидает оплаты'], ['Ожидает оплаты'], ['Ожидает оплаты']],  # Новые статусы
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

@pytest.mark.asyncio
async def test_get_user_orders_with_all_statuses(mock_orders_sheet: MagicMock):
    """Тест получения заказов пользователя со всеми доступными статусами."""
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказы пользователя с разными статусами
        ['1', '2024-04-04', 'Активен', '123', '@user1', '100', '101', 'User1', 'breakfast', 'Блюдо1', '-', '05.04.24'],
        ['2', '2024-04-04', 'Принят', '123', '@user1', '200', '102', 'User1', 'lunch', 'Блюдо2', '-', '05.04.24'],
        ['3', '2024-04-04', 'Ожидает оплаты', '123', '@user1', '300', '103', 'User1', 'dinner', 'Блюдо3', '-', '05.04.24'],
        ['4', '2024-04-04', 'Отменён', '123', '@user1', '400', '104', 'User1', 'breakfast', 'Блюдо4', '-', '05.04.24'],
        # Заказы другого пользователя
        ['5', '2024-04-04', 'Активен', '456', '@user2', '500', '105', 'User2', 'breakfast', 'Блюдо5', '-', '05.04.24'],
    ]
    
    # Настраиваем мок для get_all_values
    mock_orders_sheet.get_all_values.return_value = test_orders
    
    # Вызываем тестируемую функцию
    from orderbot.services.sheets import get_user_orders
    result = await get_user_orders('123')
    
    # Проверяем результат
    assert len(result) == 3  # Должны быть возвращены только заказы со статусами 'Активен', 'Принят' и 'Ожидает оплаты'
    
    # Проверяем статусы возвращенных заказов
    statuses = [order[2] for order in result]
    assert 'Активен' in statuses
    assert 'Принят' in statuses
    assert 'Ожидает оплаты' in statuses
    assert 'Отменён' not in statuses  # Отмененные заказы не должны возвращаться
    
    # Проверяем, что вернулись только заказы пользователя с ID '123'
    user_ids = [order[3] for order in result]
    assert all(user_id == '123' for user_id in user_ids)

@pytest.mark.asyncio
async def test_check_orders_awaiting_payment_at_startup():
    """Тест проверки и обновления статусов заказов на 'Ожидает оплаты' при запуске бота."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Заказ завтрака на сегодня со статусом Принят (должен обновиться)
        ['1', '2024-04-04', 'Принят', '1', '@user1', '100', '101', 'User1', 'Завтрак', 'Блюдо1', '-', today_str],
        # Заказ обеда на сегодня со статусом Принят (должен обновиться)
        ['2', '2024-04-04', 'Принят', '2', '@user2', '200', '102', 'User2', 'Обед', 'Блюдо2', '-', today_str],
        # Заказ ужина на сегодня со статусом Принят (не должен обновиться, т.к. еще рано)
        ['3', '2024-04-04', 'Принят', '3', '@user3', '300', '103', 'User3', 'Ужин', 'Блюдо3', '-', today_str],
        # Заказ ужина на сегодня со статусом Активен (не должен измениться)
        ['4', '2024-04-04', 'Активен', '4', '@user4', '400', '104', 'User4', 'Ужин', 'Блюдо4', '-', today_str],
    ]
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    # Используем наш собственный механизм для отслеживания обновлений
    updates_tracker = []
    
    try:
        # Устанавливаем текущее время на 14:30
        with patch('orderbot.services.sheets.datetime') as mock_dt:
            # Фиксируем дату и время
            fixed_date = datetime.now().date()
            test_time = datetime.combine(fixed_date, datetime.min.time().replace(hour=14, minute=30))
            
            # Настраиваем мок datetime
            mock_dt.now.return_value = test_time
            mock_dt.strptime = datetime.strptime
            mock_dt.combine = datetime.combine
            
            # Создаем функцию-шпион для метода update
            original_update = mock_sheet.update
            def mock_update(cell_range, values, value_input_option):
                # Извлекаем номер строки из диапазона
                if ':' in cell_range:
                    row_start = int(cell_range.split(':')[0][1:])
                    row_end = int(cell_range.split(':')[1][1:])
                    rows = list(range(row_start, row_end + 1))
                else:
                    rows = [int(cell_range[1:])]
                
                # Добавляем обновляемые строки в трекер
                updates_tracker.extend(rows)
                
                # Вызываем оригинальный метод
                return original_update(cell_range, values, value_input_option)
            
            # Заменяем метод update на наш
            mock_sheet.update = mock_update
            
            # Вызываем функцию
            result = await sheets.check_orders_awaiting_payment_at_startup()
            
            # Возвращаем оригинальный метод
            mock_sheet.update = original_update
            
            # Выводим информацию для отладки
            print(f"Обновленные строки: {updates_tracker}")
            
            # Проверяем успешное выполнение
            assert result is True
            
            # Проверяем, что были обновлены строки 2 и 3 (Завтрак и Обед)
            assert 2 in updates_tracker, "Строка 2 (Завтрак) должна быть обновлена"
            assert 3 in updates_tracker, "Строка 3 (Обед) должна быть обновлена"
            
            # Проверяем, что строка 4 (Ужин) не была обновлена
            assert 4 not in updates_tracker, "Строка 4 (Ужин со статусом Принят) не должна быть обновлена"
            assert 5 not in updates_tracker, "Строка 5 (Ужин со статусом Активен) не должна быть обновлена"
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet

@pytest.mark.asyncio
async def test_update_orders_status_non_consecutive_rows():
    """Тест обновления статусов для непоследовательных строк."""
    # Создаем мок для листа заказов
    mock_sheet = MagicMock()
    
    # Подготавливаем тестовые данные
    today = datetime.now().date()
    today_str = today.strftime("%d.%m.%y")
    
    # Создаем тестовые заказы с непоследовательными строками
    test_orders = [
        # Заголовок
        ['ID', 'Дата', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип', 'Блюда', 'Пожелания', 'Дата выдачи'],
        # Активные заказы на строках 2, 4 и 6
        ['1', '2024-04-04', 'Активен', '1', '@user1', '100', '101', 'User1', 'breakfast', 'Блюдо1', '-', today_str],
        ['2', '2024-04-04', 'Оплачен', '2', '@user2', '200', '102', 'User2', 'lunch', 'Блюдо2', '-', today_str],
        ['3', '2024-04-04', 'Активен', '3', '@user3', '300', '103', 'User3', 'dinner', 'Блюдо3', '-', today_str],
        ['4', '2024-04-04', 'Отменен', '4', '@user4', '400', '104', 'User4', 'breakfast', 'Блюдо4', '-', today_str],
        ['5', '2024-04-04', 'Активен', '5', '@user5', '500', '105', 'User5', 'lunch', 'Блюдо5', '-', today_str],
    ]
    
    # Настраиваем мок
    mock_sheet.get_all_values.return_value = test_orders
    
    # Прямо заменяем функцию get_orders_sheet в модуле
    original_get_orders_sheet = sheets.get_orders_sheet
    sheets.get_orders_sheet = lambda: mock_sheet
    
    try:
        # Вызываем тестируемую функцию
        result = await sheets.update_orders_status()
        
        # Проверяем результат
        assert result is True
        
        # Проверяем, что были выполнены обновления для каждой активной строки по отдельности
        assert mock_sheet.update.call_count == 3
        
        # Проверяем вызовы обновления для каждой строки
        mock_sheet.update.assert_any_call(
            'C2:C2',  # Строка 2
            [['Принят']],
            value_input_option='USER_ENTERED'
        )
        
        mock_sheet.update.assert_any_call(
            'C4:C4',  # Строка 4
            [['Принят']],
            value_input_option='USER_ENTERED'
        )
        
        mock_sheet.update.assert_any_call(
            'C6:C6',  # Строка 6
            [['Принят']],
            value_input_option='USER_ENTERED'
        )
    finally:
        # Восстанавливаем оригинальную функцию
        sheets.get_orders_sheet = original_get_orders_sheet 