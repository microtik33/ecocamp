"""Конфигурация для тестов."""
import os
import sys
from pathlib import Path
import pytest
import asyncio
from typing import Generator, TYPE_CHECKING
from unittest.mock import MagicMock, AsyncMock, patch

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

pytest_plugins = ["pytest_asyncio"]

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch
    from _pytest.logging import LogCaptureFixture
    from pytest_mock import MockerFixture

# Мокаем config
mock_config = MagicMock()
mock_config.BOT_TOKEN = 'fake_token'
mock_config.GOOGLE_CREDENTIALS_FILE = 'fake_credentials.json'
sys.modules['orderbot.config'] = mock_config

# Мокаем gspread
mock_gspread = MagicMock()
mock_gspread.service_account = MagicMock(return_value=MagicMock())
sys.modules['gspread'] = mock_gspread

# Создаем моки для всех листов
mock_orders_sheet = MagicMock()
mock_orders_sheet.get_all_values = MagicMock()
mock_orders_sheet.get_all_values.return_value = [
    ['ID заказа', 'Время', 'Статус', 'User ID', 'Username', 'Сумма заказа', 'Номер комнаты', 'Имя', 'Тип еды', 'Блюда', 'Пожелания', 'Дата выдачи'],
    ['1', '2023-01-01 12:00', 'Активен', '123', 'test_user', '1000', '101', 'Test User', 'breakfast', 'Блюдо 1', 'Нет', '2023-01-02']
]
mock_orders_sheet.update_cell = MagicMock()
mock_orders_sheet.find = MagicMock(return_value=MagicMock(row=2))
mock_orders_sheet.append_row = MagicMock()

mock_users_sheet = MagicMock()
mock_kitchen_sheet = MagicMock()
mock_rec_sheet = MagicMock()
mock_auth_sheet = MagicMock()
mock_menu_sheet = MagicMock()

# Патчим получение всех листов по ID
with patch('orderbot.services.sheets.spreadsheet.get_worksheet_by_id') as mock_get_worksheet:
    mock_get_worksheet.side_effect = {
        2082646960: mock_orders_sheet,
        505696272: mock_users_sheet,
        2090492372: mock_kitchen_sheet,
        1331625926: mock_rec_sheet,
        66851994: mock_auth_sheet,
        1808438200: mock_menu_sheet
    }.get
    
    mock_sheets = MagicMock()
    mock_sheets.client = MagicMock()
    mock_sheets.orders_sheet = mock_orders_sheet
    mock_sheets.users_sheet = mock_users_sheet
    mock_sheets.kitchen_sheet = mock_kitchen_sheet
    mock_sheets.rec_sheet = mock_rec_sheet
    mock_sheets.auth_sheet = mock_auth_sheet
    mock_sheets.menu_sheet = mock_menu_sheet
    mock_sheets.get_order = AsyncMock(return_value=True)
    mock_sheets.save_order = AsyncMock(return_value=True)
    mock_sheets.update_order = AsyncMock(return_value=True)
    mock_sheets.get_next_order_id = MagicMock(return_value='123')
    mock_sheets.update_orders_status = AsyncMock(return_value=True)
sys.modules['orderbot.services.sheets'] = mock_sheets

# Мокаем services.user
mock_user = MagicMock()
mock_user.update_user_info = AsyncMock(return_value=True)
mock_user.update_user_stats = AsyncMock(return_value=True)
sys.modules['orderbot.services.user'] = mock_user

# Мокаем services.auth
mock_auth = MagicMock()
mock_auth.is_user_authorized = MagicMock(return_value=True)
sys.modules['orderbot.services.auth'] = mock_auth

# Мокаем utils.time_utils
mock_time_utils = MagicMock()
mock_time_utils.is_order_time = MagicMock(return_value=True)
sys.modules['orderbot.utils.time_utils'] = mock_time_utils

# Мокаем translations
mock_translations = MagicMock()
mock_translations.get_meal_type = MagicMock(return_value='Завтрак')
mock_translations.get_button = MagicMock(return_value='Кнопка')
mock_translations.get_message = MagicMock(return_value='Сообщение')
sys.modules['orderbot.translations'] = mock_translations

# Мокаем tasks
mock_tasks = MagicMock()
mock_tasks.start_status_update_task = MagicMock()
mock_tasks.stop_status_update_task = MagicMock()
mock_tasks.schedule_daily_tasks = AsyncMock(return_value=True)
sys.modules['orderbot.tasks'] = mock_tasks

@pytest.fixture(scope="session")
def event_loop_policy() -> Generator[asyncio.AbstractEventLoopPolicy, None, None]:
    """Фикстура для настройки политики event loop."""
    policy = asyncio.WindowsSelectorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    yield policy

@pytest.fixture(autouse=True)
async def cleanup_tasks():
    """Очищает незавершенные задачи после каждого теста."""
    yield
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

@pytest.fixture(autouse=True)
def reset_mocks() -> Generator[None, None, None]:
    """Сбрасываем состояние моков перед каждым тестом."""
    mock_sheets.get_order.reset_mock()
    mock_sheets.save_order.reset_mock()
    mock_sheets.update_order.reset_mock()
    mock_sheets.get_next_order_id.reset_mock()
    mock_sheets.update_orders_status.reset_mock()
    mock_orders_sheet.get_all_values.reset_mock()
    mock_orders_sheet.update_cell.reset_mock()
    mock_orders_sheet.find.reset_mock()
    mock_orders_sheet.append_row.reset_mock()
    mock_user.update_user_info.reset_mock()
    mock_user.update_user_stats.reset_mock()
    mock_auth.is_user_authorized.reset_mock()
    mock_time_utils.is_order_time.reset_mock()
    mock_translations.get_meal_type.reset_mock()
    mock_translations.get_button.reset_mock()
    mock_translations.get_message.reset_mock()
    mock_tasks.start_status_update_task.reset_mock()
    mock_tasks.stop_status_update_task.reset_mock()
    mock_tasks.schedule_daily_tasks.reset_mock()
    yield

def pytest_addoption(parser):
    """Добавляем опции для pytest."""
    parser.addini(
        'asyncio_mode',
        'default asyncio mode',
        default='strict'
    )
    parser.addini(
        'asyncio_default_fixture_loop_scope',
        'default event loop scope for async fixtures',
        default='function'
    )
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )

def pytest_configure(config):
    """Конфигурация pytest."""
    config.inicfg['asyncio_mode'] = 'auto'
    config.inicfg['asyncio_default_fixture_loop_scope'] = 'function' 