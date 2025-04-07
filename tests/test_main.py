"""Тесты для функционала main.py."""
from typing import TYPE_CHECKING, Dict, Any, Generator
import pytest
import asyncio
import os
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from aiohttp import web, ClientSession
from telegram import Update
from telegram.ext import Application

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch
    from _pytest.logging import LogCaptureFixture
    from pytest_mock import MockerFixture

@pytest.fixture(autouse=True)
def reset_mocks():
    """Сбрасываем состояние моков перед каждым тестом."""
    mock_tasks.start_status_update_task.reset_mock()
    mock_tasks.stop_status_update_task.reset_mock()
    mock_tasks.schedule_daily_tasks.reset_mock()
    mock_records.process_daily_orders.reset_mock()

# Мокаем необходимые модули перед импортом main
mock_config = MagicMock()
mock_config.BOT_TOKEN = 'fake_token'
mock_config.GOOGLE_CREDENTIALS_FILE = 'fake_credentials.json'
sys.modules['config'] = mock_config

# Мокаем gspread
mock_gspread = MagicMock()
mock_gspread.service_account = MagicMock(return_value=MagicMock())
sys.modules['gspread'] = mock_gspread

# Создаем корутину для schedule_daily_tasks
async def mock_schedule_daily_tasks():
    """Мок для schedule_daily_tasks."""
    pass

mock_tasks = MagicMock()
mock_tasks.start_status_update_task = MagicMock()
mock_tasks.stop_status_update_task = MagicMock()
mock_tasks.schedule_daily_tasks = AsyncMock(side_effect=mock_schedule_daily_tasks)
sys.modules['tasks'] = mock_tasks

mock_records = MagicMock()
mock_records.process_daily_orders = AsyncMock()
sys.modules['services.records'] = mock_records

mock_handlers = MagicMock()
mock_handlers.auth_start = AsyncMock()
mock_handlers.handle_phone = AsyncMock()
mock_handlers.kitchen_summary = AsyncMock()
sys.modules['handlers.auth'] = mock_handlers
sys.modules['handlers.kitchen'] = mock_handlers

mock_order = MagicMock()
mock_order.PHONE = 'PHONE'
mock_order.MENU = 'MENU'
mock_order.ROOM = 'ROOM'
mock_order.NAME = 'NAME'
mock_order.MEAL_TYPE = 'MEAL_TYPE'
mock_order.DISH_SELECTION = 'DISH_SELECTION'
mock_order.WISHES = 'WISHES'
mock_order.QUESTION = 'QUESTION'
mock_order.ask_room = AsyncMock()
mock_order.show_user_orders = AsyncMock()
mock_order.handle_question = AsyncMock()
mock_order.cancel_order = AsyncMock()
mock_order.ask_name = AsyncMock()
mock_order.handle_order_update = AsyncMock()
mock_order.ask_meal_type = AsyncMock()
mock_order.show_dishes = AsyncMock()
mock_order.handle_dish_selection = AsyncMock()
mock_order.handle_text_input = AsyncMock()
mock_order.save_question = AsyncMock()
mock_order.handle_order_time_error = AsyncMock()
mock_order.show_edit_active_orders = AsyncMock()
mock_order.start_new_order = AsyncMock()
sys.modules['handlers.order'] = mock_order

# Мокаем services.sheets
mock_sheets = MagicMock()
mock_sheets.client = MagicMock()
mock_sheets.orders_sheet = MagicMock()
mock_sheets.users_sheet = MagicMock()
sys.modules['services.sheets'] = mock_sheets

# Мокаем services.user
mock_user = MagicMock()
mock_user.update_user_info = AsyncMock()
sys.modules['services.user'] = mock_user

# Мокаем handlers.menu
mock_menu = MagicMock()
mock_menu.start = AsyncMock()
sys.modules['handlers.menu'] = mock_menu

from orderbot import main

@pytest.fixture
def mock_env_vars(monkeypatch: 'MonkeyPatch') -> None:
    """Фикстура для установки переменных окружения."""
    monkeypatch.setenv('RENDER_EXTERNAL_URL', 'https://test-bot.example.com')
    monkeypatch.setenv('PORT', '8080')
    monkeypatch.setenv('WEBHOOK_SECRET', 'test-secret-token')

@pytest.fixture
def mock_application() -> MagicMock:
    """Фикстура для создания мока Application."""
    app = MagicMock(spec=Application)
    app.builder = MagicMock()
    app.builder.token = MagicMock(return_value=app.builder)
    app.builder.build = MagicMock(return_value=app)
    app.initialize = AsyncMock()
    app.add_handler = MagicMock()
    app.bot = MagicMock()
    app.bot.set_webhook = AsyncMock()
    app.update_queue = MagicMock()
    app.update_queue.put = AsyncMock()
    app.start = AsyncMock()
    app.shutdown = AsyncMock()
    app.run_polling = AsyncMock()
    return app

@pytest.fixture
def mock_web_app() -> MagicMock:
    """Фикстура для создания мока web.Application."""
    app = MagicMock(spec=web.Application)
    app.router = MagicMock()
    app.router.add_post = MagicMock()
    app.router.add_get = MagicMock()
    return app

@pytest.fixture
def mock_runner() -> MagicMock:
    """Фикстура для создания мока AppRunner."""
    runner = MagicMock()
    runner.setup = AsyncMock()
    return runner

@pytest.fixture
def mock_site() -> MagicMock:
    """Фикстура для создания мока TCPSite."""
    site = MagicMock()
    site.start = AsyncMock()
    return site

@pytest.mark.asyncio
async def test_keep_alive_with_webhook_url(
    mock_env_vars: None,
    mock_application: MagicMock,
    mocker: 'MockerFixture'
) -> None:
    """Тест функции keep_alive с установленным webhook_url."""
    # Создаем мок для ClientSession
    mock_session = AsyncMock(spec=ClientSession)
    mock_session.__aenter__.return_value = mock_session
    
    # Создаем мок для response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_session.get.return_value = mock_response
    mock_response.__aenter__.return_value = mock_response
    
    # Патчим ClientSession
    mocker.patch('aiohttp.ClientSession', return_value=mock_session)
    
    # Патчим asyncio.sleep
    mock_sleep = AsyncMock(side_effect=asyncio.TimeoutError)
    mocker.patch('asyncio.sleep', mock_sleep)
    
    # Патчим asyncio.shield
    async def mock_shield_func(coro):
        try:
            return await coro
        except Exception:
            pass
    mock_shield = AsyncMock(side_effect=mock_shield_func)
    mocker.patch('asyncio.shield', mock_shield)
    
    # Патчим Application.builder
    mocker.patch('telegram.ext.Application.builder', return_value=mock_application.builder)
    
    # Патчим sys.exit
    mock_exit = mocker.patch('sys.exit')
    
    # Патчим asyncio.Event().wait
    mock_event = AsyncMock()
    mock_event.wait = AsyncMock(side_effect=asyncio.TimeoutError)
    mocker.patch('asyncio.Event', return_value=mock_event)
    
    # Запускаем функцию
    await main.main()
    
    # Проверяем, что был вызван sys.exit с кодом 1
    mock_exit.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_keep_alive_without_webhook_url(
    monkeypatch: 'MonkeyPatch'
) -> None:
    """Тест функции keep_alive без установленного webhook_url."""
    # Удаляем переменную окружения
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    
    # Функция должна завершиться сразу
    await main.keep_alive()
    
    # Никаких дополнительных проверок не требуется, так как функция должна просто вернуться

@pytest.mark.asyncio
async def test_keep_alive_with_error(
    mock_env_vars: None,
    mocker: 'MockerFixture'
) -> None:
    """Тест функции keep_alive с ошибкой при запросе."""
    # Создаем мок для ClientSession
    mock_session = AsyncMock(spec=ClientSession)
    mock_session.__aenter__.return_value = mock_session
    
    # Настраиваем мок для вызова исключения
    mock_session.get.side_effect = Exception("Test error")
    
    # Патчим ClientSession
    mocker.patch('aiohttp.ClientSession', return_value=mock_session)
    
    # Патчим asyncio.sleep
    mock_sleep = AsyncMock(side_effect=asyncio.TimeoutError)
    mocker.patch('asyncio.sleep', mock_sleep)
    
    # Патчим asyncio.shield
    mock_shield = AsyncMock(side_effect=lambda x: x)
    mocker.patch('asyncio.shield', mock_shield)
    
    # Патчим asyncio.create_task
    mock_task = AsyncMock()
    mock_task.cancel = AsyncMock()
    mock_create_task = MagicMock(return_value=mock_task)
    mocker.patch('asyncio.create_task', mock_create_task)
    
    # Запускаем функцию
    try:
        await main.keep_alive()
    except asyncio.TimeoutError:
        pass
    
    # Проверяем, что был вызван sleep с меньшим интервалом
    mock_sleep.assert_called_with(60)

@pytest.mark.asyncio
async def test_main_with_webhook(
    mock_env_vars: None,
    mock_application: MagicMock,
    mock_web_app: MagicMock,
    mock_runner: MagicMock,
    mock_site: MagicMock,
    mocker: 'MockerFixture'
) -> None:
    """Тест функции main с использованием webhook."""
    # Патчим Application.builder
    mocker.patch('telegram.ext.Application.builder', return_value=mock_application.builder)
    
    # Патчим web.Application
    mocker.patch('aiohttp.web.Application', return_value=mock_web_app)
    
    # Патчим AppRunner
    mocker.patch('aiohttp.web.AppRunner', return_value=mock_runner)
    
    # Патчим TCPSite
    mocker.patch('aiohttp.web.TCPSite', return_value=mock_site)
    
    # Патчим asyncio.Event().wait
    mock_event = AsyncMock()
    mock_event.wait = AsyncMock(side_effect=asyncio.TimeoutError)
    mocker.patch('asyncio.Event', return_value=mock_event)
    
    # Патчим sys.exit
    mock_exit = mocker.patch('sys.exit')
    
    # Запускаем функцию
    try:
        await main.main()
    except asyncio.TimeoutError:
        pass
    
    # Проверяем, что были вызваны необходимые методы
    mock_application.initialize.assert_called_once()
    mock_tasks.start_status_update_task.assert_called_once()
    mock_application.add_handler.assert_called()
    mock_tasks.schedule_daily_tasks.assert_called_once()
    mock_records.process_daily_orders.assert_called_once()
    mock_application.bot.set_webhook.assert_called_once_with(
        url="https://test-bot.example.com/webhook",
        secret_token="test-secret-token"
    )
    mock_web_app.router.add_post.assert_called()
    mock_web_app.router.add_get.assert_called()
    mock_runner.setup.assert_called_once()
    mock_site.start.assert_called_once()
    mock_application.start.assert_called_once()

@pytest.mark.asyncio
async def test_main_without_webhook(
    monkeypatch: 'MonkeyPatch',
    mock_application: MagicMock,
    mocker: 'MockerFixture'
) -> None:
    """Тест функции main без использования webhook."""
    # Удаляем переменную окружения
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    
    # Патчим Application.builder
    mocker.patch('telegram.ext.Application.builder', return_value=mock_application.builder)
    
    # Запускаем функцию
    await main.main()
    
    # Проверяем, что были вызваны необходимые методы
    mock_application.initialize.assert_called_once()
    mock_tasks.start_status_update_task.assert_called_once()
    mock_application.add_handler.assert_called()
    mock_tasks.schedule_daily_tasks.assert_called_once()
    mock_records.process_daily_orders.assert_called_once()
    mock_application.run_polling.assert_called_once_with(allowed_updates=Update.ALL_TYPES)

@pytest.mark.asyncio
async def test_main_with_exception(
    mock_application: MagicMock,
    mocker: 'MockerFixture'
) -> None:
    """Тест функции main с исключением."""
    # Патчим Application.builder
    mocker.patch('telegram.ext.Application.builder', return_value=mock_application.builder)
    
    # Настраиваем мок для вызова исключения
    mock_application.initialize.side_effect = Exception("Test error")
    
    # Патчим sys.exit
    mock_exit = mocker.patch('sys.exit')
    
    # Патчим asyncio.create_task
    mock_task = AsyncMock()
    mock_task.cancel = AsyncMock()
    mock_create_task = MagicMock(return_value=mock_task)
    mocker.patch('asyncio.create_task', mock_create_task)
    
    # Патчим asyncio.shield
    async def mock_shield_func(coro):
        try:
            return await coro
        except Exception:
            pass
    mock_shield = AsyncMock(side_effect=mock_shield_func)
    mocker.patch('asyncio.shield', mock_shield)
    
    # Сбрасываем счетчик вызовов для stop_status_update_task
    mock_tasks.stop_status_update_task.reset_mock()
    
    # Запускаем функцию
    await main.main()
    
    # Проверяем, что были вызваны необходимые методы
    mock_application.initialize.assert_called_once()
    mock_tasks.stop_status_update_task.assert_called_once()
    mock_application.shutdown.assert_called_once()
    mock_exit.assert_called_once_with(1)

def test_main_sync_with_keyboard_interrupt(
    mocker: 'MockerFixture'
) -> None:
    """Тест функции main_sync с KeyboardInterrupt."""
    # Патчим asyncio.run
    mock_run = mocker.patch('asyncio.run')
    mock_run.side_effect = KeyboardInterrupt()
    
    # Патчим sys.exit
    mock_exit = mocker.patch('sys.exit')
    
    # Запускаем функцию
    main.main_sync()
    
    # Проверяем, что были вызваны необходимые методы
    mock_run.assert_called_once()
    mock_exit.assert_called_once_with(0)

def test_main_sync_with_exception(
    mocker: 'MockerFixture'
) -> None:
    """Тест функции main_sync с исключением."""
    # Патчим asyncio.run
    mock_run = mocker.patch('asyncio.run')
    mock_run.side_effect = Exception("Test error")
    
    # Запускаем функцию и проверяем, что исключение пробрасывается дальше
    with pytest.raises(Exception, match="Test error"):
        main.main_sync()
    
    # Проверяем, что был вызван asyncio.run
    mock_run.assert_called_once() 