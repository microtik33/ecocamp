"""Tests for records.py module."""
from typing import Any, List, TYPE_CHECKING
import pytest
from datetime import datetime, date
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture

@pytest.fixture(autouse=True)
def mock_gspread():
    """Фикстура для мока gspread."""
    with patch('gspread.service_account') as mock_service:
        mock_client = MagicMock()
        mock_service.return_value = mock_client
        yield mock_client

@pytest.fixture
def mock_sheets(mock_gspread):
    """Фикстура для мока Google Sheets."""
    with patch('orderbot.services.records.orders_sheet') as mock_orders, \
         patch('orderbot.services.records.rec_sheet') as mock_rec:
        
        # Настраиваем мок для orders_sheet
        mock_orders.get_all_values.return_value = [
            ['ID', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
            ['1', '01.04.2025', 'Принят', '123', 'user1', '200', '1', 'John', 'breakfast', 'Каша x2', '-', '2025-04-01'],
            ['2', '01.04.2025', 'Принят', '124', 'user2', '200', '2', 'Mike', 'lunch', 'Борщ x1', '-', '2025-04-01'],
            ['3', '01.04.2025', 'Принят', '125', 'user3', '200', '3', 'Alex', 'dinner', 'Рыба x1', '-', '2025-04-01'],
            ['4', '01.04.2025', 'Отменён', '126', 'user4', '200', '4', 'Sam', 'breakfast', 'Каша x1', '-', '2025-04-01']
        ]
        
        # Настраиваем мок для rec_sheet
        mock_rec.get_all_values.return_value = [
            ['Дата выдачи', 'Количество заказов', 'Количество отмен', 'Общая сумма', 'Завтрак', 'Обед', 'Ужин']
        ]
        
        yield {
            'orders': mock_orders,
            'rec': mock_rec
        }

@pytest.mark.asyncio
async def test_process_daily_orders_success(mock_sheets: dict[str, MagicMock]):
    """Тест успешной обработки заказов за день."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем фиксированную дату для теста
    with patch('orderbot.services.records.date') as mock_date:
        mock_date.today.return_value = date(2025, 4, 1)
        mock_date.strftime = date.strftime
        
        # Вызываем тестируемую функцию
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что данные были получены
        mock_sheets['orders'].get_all_values.assert_called_once()
        mock_sheets['rec'].get_all_values.assert_called_once()
        
        # Проверяем, что была попытка обновить или добавить запись
        assert mock_sheets['rec'].update.called or mock_sheets['rec'].append_row.called
        
        # Если запись добавлялась, проверяем корректность данных
        if mock_sheets['rec'].append_row.called:
            call_args = mock_sheets['rec'].append_row.call_args[0][0]
            assert call_args[0] == '01.04.25'  # Дата в формате DD.MM.YY
            assert call_args[1] == '3'  # Количество принятых заказов
            assert call_args[2] == '1'  # Количество отменённых заказов
            assert call_args[3] == '600'  # Общая сумма
            assert 'Каша x2' in call_args[4]  # Завтрак
            assert 'Борщ x1' in call_args[5]  # Обед
            assert 'Рыба x1' in call_args[6]  # Ужин

@pytest.mark.asyncio
async def test_process_daily_orders_no_orders(mock_sheets: dict[str, MagicMock]):
    """Тест обработки при отсутствии заказов за день."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем пустой список заказов
    mock_sheets['orders'].get_all_values.return_value = [
        ['ID', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи']
    ]
    
    # Вызываем тестируемую функцию
    result = await process_daily_orders()
    
    # Проверяем, что функция завершилась без ошибок
    assert result is None
    
    # Проверяем, что не было попыток обновить таблицу
    assert not mock_sheets['rec'].update.called
    assert not mock_sheets['rec'].append_row.called

@pytest.mark.asyncio
async def test_process_daily_orders_error_handling(mock_sheets: dict[str, MagicMock]):
    """Тест обработки ошибок."""
    from orderbot.services.records import process_daily_orders
    
    # Имитируем ошибку при получении данных
    mock_sheets['orders'].get_all_values.side_effect = Exception("Test error")
    
    # Вызываем тестируемую функцию
    result = await process_daily_orders()
    
    # Проверяем, что функция вернула False при ошибке
    assert result is False
    
    # Проверяем, что не было попыток обновить таблицу
    assert not mock_sheets['rec'].update.called
    assert not mock_sheets['rec'].append_row.called

@pytest.mark.asyncio
async def test_process_daily_orders_empty_rec_sheet(mock_sheets: dict[str, MagicMock]):
    """Тест создания заголовков в пустой таблице Rec."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем пустую таблицу Rec
    mock_sheets['rec'].get_all_values.return_value = []
    
    # Устанавливаем фиксированную дату
    with patch('orderbot.services.records.date') as mock_date:
        mock_date.today.return_value = date(2025, 4, 1)
        mock_date.strftime = date.strftime
        
        # Вызываем тестируемую функцию
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что были добавлены заголовки
        mock_sheets['rec'].append_row.assert_any_call(
            ['Дата выдачи', 'Количество заказов', 'Количество отмен', 'Общая сумма', 'Завтрак', 'Обед', 'Ужин'],
            value_input_option='USER_ENTERED'
        )
        
        # Проверяем, что данные были добавлены с правильной датой
        calls = mock_sheets['rec'].append_row.call_args_list
        assert len(calls) == 2  # Один вызов для заголовков, один для данных
        data_call = calls[1]
        assert data_call[0][0][0] == '01.04.25'  # Проверяем формат даты

@pytest.mark.asyncio
async def test_process_daily_orders_update_existing(mock_sheets: dict[str, MagicMock]):
    """Тест обновления существующей записи в таблице Rec."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем существующую запись
    mock_sheets['rec'].get_all_values.return_value = [
        ['Дата выдачи', 'Количество заказов', 'Количество отмен', 'Общая сумма', 'Завтрак', 'Обед', 'Ужин'],
        ['01.04.25', '2', '0', '400', 'Каша x1', '—', '—']
    ]
    
    # Устанавливаем фиксированную дату
    with patch('orderbot.services.records.date') as mock_date:
        mock_date.today.return_value = date(2025, 4, 1)
        mock_date.strftime = date.strftime
        
        # Вызываем тестируемую функцию
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что была попытка обновить запись
        mock_sheets['rec'].update.assert_called_once()
        
        # Проверяем данные обновления
        call_args = mock_sheets['rec'].update.call_args[0]
        assert call_args[1][0][0] == '01.04.25'  # Проверяем формат даты

@pytest.mark.asyncio
async def test_process_daily_orders_different_date_formats(mock_sheets: dict[str, MagicMock]):
    """Тест обработки заказов с разными форматами дат."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем заказы с разными форматами дат
    mock_sheets['orders'].get_all_values.return_value = [
        ['ID', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
        ['1', '01.04.2025', 'Принят', '123', 'user1', '100', '1', 'John', 'breakfast', 'Каша x2', '-', '2025-04-01'],
        ['2', '01.04.2025', 'Принят', '124', 'user2', '150', '2', 'Mike', 'lunch', 'Суп x1', '-', '01.04.25'],
        ['3', '01.04.2025', 'Принят', '125', 'user3', '200', '3', 'Alex', 'dinner', 'Рыба x1', '-', '1.4.2025']
    ]
    
    # Устанавливаем фиксированную дату
    with patch('orderbot.services.records.date') as mock_date:
        mock_date.today.return_value = date(2025, 4, 1)
        mock_date.strftime = date.strftime
        
        # Вызываем тестируемую функцию
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что все заказы были обработаны
        if mock_sheets['rec'].append_row.called:
            call_args = mock_sheets['rec'].append_row.call_args[0][0]
            assert call_args[0] == '01.04.25'  # Дата в формате DD.MM.YY
            assert call_args[1] == '3'  # Количество принятых заказов
            assert call_args[2] == '0'  # Количество отменённых заказов
            assert call_args[3] == '450'  # Общая сумма
            assert 'Каша x2' in call_args[4]  # Завтрак
            assert 'Суп x1' in call_args[5]  # Обед
            assert 'Рыба x1' in call_args[6]  # Ужин

@pytest.mark.asyncio
async def test_process_daily_orders_meal_counting(mock_sheets: dict[str, MagicMock]):
    """Тест подсчета блюд по типам приема пищи."""
    from orderbot.services.records import process_daily_orders
    
    # Устанавливаем тестовые данные с разными типами еды
    mock_sheets['orders'].get_all_values.return_value = [
        ['ID', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
        ['1', '01.04.2025', 'Принят', '123', 'user1', '100', '1', 'John', 'breakfast', 'Каша x2, Яйца x1', '-', '2025-04-01'],
        ['2', '01.04.2025', 'Принят', '124', 'user2', '150', '2', 'Mike', 'lunch', 'Суп x1, Салат x2', '-', '01.04.25'],
        ['3', '01.04.2025', 'Принят', '125', 'user3', '200', '3', 'Alex', 'dinner', 'Рыба x1, Гарнир x2', '-', '1.4.2025'],
        ['4', '01.04.2025', 'Отменён', '126', 'user4', '100', '4', 'Sam', 'breakfast', 'Каша x1', '-', '2025-04-01']
    ]
    
    # Устанавливаем фиксированную дату
    with patch('orderbot.services.records.date') as mock_date:
        mock_date.today.return_value = date(2025, 4, 1)
        mock_date.strftime = date.strftime
        
        # Вызываем тестируемую функцию
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что все заказы были обработаны
        if mock_sheets['rec'].append_row.called:
            call_args = mock_sheets['rec'].append_row.call_args[0][0]
            assert call_args[0] == '01.04.25'  # Дата
            assert call_args[1] == '3'  # Количество принятых заказов
            assert call_args[2] == '1'  # Количество отменённых заказов
            assert call_args[3] == '450'  # Общая сумма
            
            # Проверяем подсчет блюд по типам приема пищи
            assert 'Каша x2' in call_args[4]  # Завтрак
            assert 'Яйца x1' in call_args[4]
            assert 'Суп x1' in call_args[5]  # Обед
            assert 'Салат x2' in call_args[5]
            assert 'Рыба x1' in call_args[6]  # Ужин
            assert 'Гарнир x2' in call_args[6]
            
            # Проверяем, что отмененные заказы не учитываются
            assert 'Каша x1' not in call_args[4]  # Отмененный заказ не должен учитываться 

@pytest.mark.asyncio
async def test_process_daily_orders_at_midnight(mock_sheets: dict[str, MagicMock]):
    """Тест обработки заказов в полночь."""
    from orderbot.services.records import process_daily_orders
    
    # Мокаем datetime.now() чтобы имитировать полночь
    mock_now = MagicMock()
    mock_now.return_value = datetime(2024, 4, 8, 0, 0, 0)
    
    # Настраиваем мок для orders_sheet
    mock_sheets['orders'].get_all_values.return_value = [
        ['ID заказа', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
        ['1', '10:00', 'Активен', '123', 'user1', '1000', '101', 'Иван', 'breakfast', 'Омлет x2, Кофе x1', '', '2024-04-07'],
        ['2', '11:00', 'Принят', '456', 'user2', '1500', '102', 'Петр', 'lunch', 'Суп x1, Стейк x1', '', '2024-04-07'],
        ['3', '12:00', 'Отменён', '789', 'user3', '2000', '103', 'Сергей', 'dinner', 'Салат x1, Рыба x1', '', '2024-04-07'],
        ['4', '13:00', 'Активен', '321', 'user4', '1200', '104', 'Анна', 'breakfast', 'Блинчики x2, Чай x1', '', '2024-04-08']
    ]
    
    # Настраиваем мок для rec_sheet
    mock_sheets['rec'].get_all_values.return_value = [
        ['Дата выдачи', 'Количество заказов', 'Количество отмен', 'Общая сумма', 'Завтрак', 'Обед', 'Ужин'],
        ['07.04.24', '2', '1', '2500', 'Омлет x2, Кофе x1', 'Суп x1, Стейк x1', '—']
    ]
    
    with patch('orderbot.services.records.datetime') as mock_datetime:
        mock_datetime.now = mock_now
        mock_datetime.today.return_value = datetime(2024, 4, 8).date()
        
        # Запускаем обработку заказов
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что были получены все заказы
        mock_sheets['orders'].get_all_values.assert_called_once()
        
        # Проверяем, что были получены записи из таблицы Rec
        mock_sheets['rec'].get_all_values.assert_called_once()
        
        # Проверяем, что была добавлена новая запись
        mock_sheets['rec'].append_row.assert_called_once()
        
        # Получаем аргументы вызова append_row
        call_args = mock_sheets['rec'].append_row.call_args
        row_data = call_args[0][0]
        
        # Проверяем содержимое новой записи
        assert row_data[0] == '08.04.24'  # Дата
        assert row_data[1] == '1'  # Количество заказов
        assert row_data[2] == '0'  # Количество отмен
        assert row_data[3] == '1200'  # Общая сумма
        assert row_data[4] == 'Блинчики x2, Чай x1'  # Завтрак
        assert row_data[5] == '—'  # Обед
        assert row_data[6] == '—'  # Ужин

@pytest.mark.asyncio
async def test_process_daily_orders_with_status_change(mock_sheets: dict[str, MagicMock]):
    """Тест обработки заказов с изменением статуса."""
    from orderbot.services.records import process_daily_orders
    
    # Мокаем datetime.now() чтобы имитировать полночь
    mock_now = MagicMock()
    mock_now.return_value = datetime(2024, 4, 7, 0, 0, 0)
    
    # Настраиваем мок для orders_sheet
    mock_sheets['orders'].get_all_values.return_value = [
        ['ID заказа', 'Время', 'Статус', 'User ID', 'Username', 'Сумма', 'Комната', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
        ['1', '10:00', 'Активен', '123', 'user1', '1000', '101', 'Иван', 'breakfast', 'Омлет x2, Кофе x1', '', '2024-04-07'],
        ['2', '11:00', 'Принят', '456', 'user2', '1500', '102', 'Петр', 'lunch', 'Суп x1, Стейк x1', '', '2024-04-07'],
        ['3', '12:00', 'Отменён', '789', 'user3', '2000', '103', 'Сергей', 'dinner', 'Салат x1, Рыба x1', '', '2024-04-07']
    ]
    
    with patch('orderbot.services.records.datetime') as mock_datetime:
        mock_datetime.now = mock_now
        mock_datetime.today.return_value = datetime(2024, 4, 7).date()
        
        # Запускаем обработку заказов
        result = await process_daily_orders()
        
        # Проверяем, что функция вернула True
        assert result is True
        
        # Проверяем, что были получены все заказы
        mock_sheets['orders'].get_all_values.assert_called_once()
        
        # Проверяем, что были получены записи из таблицы Rec
        mock_sheets['rec'].get_all_values.assert_called_once()
        
        # Проверяем, что была обновлена существующая запись
        mock_sheets['rec'].update.assert_called_once()
        
        # Получаем аргументы вызова update
        call_args = mock_sheets['rec'].update.call_args
        range_name = call_args[0][0]
        row_data = call_args[0][1][0]
        
        # Проверяем содержимое обновленной записи
        assert row_data[0] == '07.04.24'  # Дата
        assert row_data[1] == '2'  # Количество заказов (Активен + Принят)
        assert row_data[2] == '1'  # Количество отмен
        assert row_data[3] == '2500'  # Общая сумма (1000 + 1500)
        assert row_data[4] == 'Омлет x2, Кофе x1'  # Завтрак
        assert row_data[5] == 'Суп x1, Стейк x1'  # Обед
        assert row_data[6] == '—'  # Ужин (отменен) 