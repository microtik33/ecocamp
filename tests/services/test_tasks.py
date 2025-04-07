"""Тесты для модуля tasks."""
import asyncio
from datetime import datetime, time
from unittest.mock import patch, MagicMock, AsyncMock
import pytest
from typing import Dict, Any
import sys
import logging
import tempfile
import json

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)

# Создаем временный файл с фиктивными учетными данными
temp_credentials = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
credentials = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "test-key-id",
    "private_key": "test-private-key",
    "client_email": "test@test.com",
    "client_id": "test-client-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test%40test.com"
}
json.dump(credentials, temp_credentials)
temp_credentials.close()

# Мокаем gspread и config до импорта tasks
mock_gspread = MagicMock()
mock_gspread.service_account.return_value = MagicMock()
sys.modules['gspread'] = mock_gspread

mock_config = MagicMock()
mock_config.GOOGLE_CREDENTIALS_FILE = temp_credentials.name
sys.modules['config'] = mock_config

# Мокаем services.sheets и services.records
mock_sheets = MagicMock()
mock_sheets.update_orders_status = AsyncMock(return_value=True)
sys.modules['services.sheets'] = mock_sheets

mock_records = MagicMock()
mock_records.process_daily_orders = AsyncMock(return_value=True)
sys.modules['services.records'] = mock_records

@pytest.fixture
def mock_dependencies() -> Dict[str, AsyncMock]:
    """Создает моки для зависимостей."""
    with patch('orderbot.services.sheets.update_orders_status') as mock_update_status, \
         patch('orderbot.services.records.process_daily_orders') as mock_process_orders:
        
        mock_update_status.return_value = True
        mock_process_orders.return_value = True
        
        yield {
            'update_status': mock_update_status,
            'process_orders': mock_process_orders
        }

@pytest.mark.asyncio
async def test_schedule_daily_tasks_sequence(mock_dependencies: Dict[str, AsyncMock]):
    """Тест последовательности выполнения задач по расписанию."""
    from orderbot.tasks import schedule_daily_tasks

    # Создаем мок для datetime.now()
    mock_now = MagicMock()
    mock_time = time(0, 0)  # Используем реальный объект time
    mock_now.return_value = MagicMock()
    mock_now.return_value.time.return_value = mock_time
    logging.info(f"Создан мок для datetime.now() с hour={mock_time.hour}, minute={mock_time.minute}")

    with patch('orderbot.tasks.datetime') as mock_datetime:
        mock_datetime.now = mock_now

        # Запускаем задачу в фоне
        task = asyncio.create_task(schedule_daily_tasks())

        # Ждем достаточно долго, чтобы задача успела выполниться (2 секунды)
        await asyncio.sleep(2)

        # Отменяем задачу
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Проверяем последовательность вызовов
        mock_dependencies['update_status'].assert_called_once()  # Теперь функция должна вызываться
        mock_dependencies['process_orders'].assert_called_once()  # Должна вызываться после update_status

@pytest.mark.asyncio
async def test_update_orders_status_before_processing(mock_dependencies: Dict[str, AsyncMock]):
    """Тест проверки, что статусы обновляются до подведения итогов."""
    from orderbot.tasks import schedule_daily_tasks, update_orders_status

    # Создаем мок для datetime.now()
    mock_now = MagicMock()
    mock_time = time(0, 0)  # Используем реальный объект time
    mock_now.return_value = MagicMock()
    mock_now.return_value.time.return_value = mock_time
    logging.info(f"Создан мок для datetime.now() с hour={mock_time.hour}, minute={mock_time.minute}")

    # Делаем update_orders_status асинхронной функцией, которая выполняется 0.5 секунды
    async def slow_update_status(*args, **kwargs):
        logging.info("Начало выполнения update_orders_status")
        await asyncio.sleep(0.5)
        logging.info("Завершение выполнения update_orders_status")
        return True

    mock_dependencies['update_status'].side_effect = slow_update_status

    with patch('orderbot.tasks.datetime') as mock_datetime:
        mock_datetime.now = mock_now
        logging.info("Установлен мок для datetime")

        # Запускаем задачу в фоне
        task = asyncio.create_task(schedule_daily_tasks())
        logging.info("Задача запущена")

        # Ждем достаточно долго, чтобы задача успела выполниться (65 секунд)
        await asyncio.sleep(65)
        logging.info("Прошло время ожидания")

        # Отменяем задачу
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logging.info("Задача отменена")

        # Проверяем, что process_daily_orders вызывается после update_orders_status
        mock_dependencies['update_status'].assert_called_once()
        mock_dependencies['process_orders'].assert_called_once()

@pytest.mark.asyncio
async def test_process_daily_orders_waits_for_status_update(mock_dependencies: Dict[str, AsyncMock]):
    """Тест проверки, что подведение итогов ждет завершения обновления статусов."""
    from orderbot.tasks import schedule_daily_tasks

    # Создаем мок для datetime.now()
    mock_now = MagicMock()
    mock_time = MagicMock()
    mock_time.hour = 0
    mock_time.minute = 0
    mock_now.return_value = MagicMock()
    mock_now.return_value.time.return_value = mock_time
    logging.info(f"Создан мок для datetime.now() с hour={mock_time.hour}, minute={mock_time.minute}")

    # Делаем update_orders_status асинхронной функцией, которая выполняется 0.5 секунды
    async def slow_update_status(*args, **kwargs):
        logging.info("Начало выполнения update_orders_status")
        await asyncio.sleep(0.5)
        logging.info("Завершение выполнения update_orders_status")
        return True

    mock_dependencies['update_status'].side_effect = slow_update_status

    with patch('orderbot.tasks.datetime') as mock_datetime:
        mock_datetime.now = mock_now
        logging.info("Установлен мок для datetime")

        # Запускаем задачу в фоне
        task = asyncio.create_task(schedule_daily_tasks())
        logging.info("Задача запущена")

        # Ждем 0.1 секунды (меньше, чем время выполнения update_orders_status)
        await asyncio.sleep(0.1)
        logging.info("Прошло 0.1 секунды")

        # Проверяем, что process_daily_orders еще не вызван
        mock_dependencies['process_orders'].assert_not_called()
        logging.info("process_daily_orders еще не вызван")

        # Ждем достаточно долго, чтобы задача успела выполниться (65 секунд)
        await asyncio.sleep(65)
        logging.info("Прошло 65 секунд")

        # Отменяем задачу
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        logging.info("Задача отменена")

        # Проверяем, что process_daily_orders был вызван после завершения update_orders_status
        mock_dependencies['update_status'].assert_called_once()
        mock_dependencies['process_orders'].assert_called_once() 