import time
import logging
import functools
import inspect
import asyncio
from typing import Callable, Any, Dict, List, Tuple

# Хранилище для статистики времени выполнения функций
execution_stats: Dict[str, List[float]] = {}

def profile_time(func: Callable) -> Callable:
    """
    Декоратор для измерения времени выполнения функций.
    
    Записывает время выполнения функции в глобальный словарь execution_stats
    и логирует результаты.
    
    Args:
        func: Функция для профилирования
        
    Returns:
        Обернутая функция с измерением времени выполнения
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed_time = time.time() - start_time
            func_name = f"{func.__module__}.{func.__name__}"
            
            if func_name not in execution_stats:
                execution_stats[func_name] = []
            
            execution_stats[func_name].append(elapsed_time)
            
            logging.info(f"Выполнение {func_name} заняло {elapsed_time:.3f} сек")
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed_time = time.time() - start_time
            func_name = f"{func.__module__}.{func.__name__}"
            
            if func_name not in execution_stats:
                execution_stats[func_name] = []
            
            execution_stats[func_name].append(elapsed_time)
            
            logging.info(f"Выполнение {func_name} заняло {elapsed_time:.3f} сек")
    
    # Выбираем подходящий враппер в зависимости от типа функции
    if asyncio_is_coroutine_function(func):
        return async_wrapper
    return sync_wrapper

def asyncio_is_coroutine_function(func):
    """Проверяет, является ли функция корутиной"""
    return inspect.iscoroutinefunction(func)

def get_execution_stats() -> Dict[str, Dict[str, float]]:
    """
    Возвращает статистику времени выполнения функций.
    
    Returns:
        Dict: Словарь со статистикой для каждой функции
              (минимальное, максимальное и среднее время выполнения)
    """
    result = {}
    
    for func_name, times in execution_stats.items():
        if not times:
            continue
            
        result[func_name] = {
            "min": min(times),
            "max": max(times),
            "avg": sum(times) / len(times),
            "count": len(times),
            "total": sum(times)
        }
    
    return result

def clear_stats():
    """Очищает собранную статистику"""
    execution_stats.clear() 