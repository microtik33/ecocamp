"""Конфигурация для тестов."""
import os
import sys
from pathlib import Path
import pytest
import asyncio
from typing import Generator

# Добавляем корневую директорию проекта в PYTHONPATH
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

pytest_plugins = ["pytest_asyncio"]

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