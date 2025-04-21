"""
Вспомогательные функции, собранные из различных модулей утилит.

Этот модуль служит единой точкой импорта часто используемых функций из разных модулей
пакета utils, чтобы упростить их использование в других частях приложения.
"""

from .markdown_utils import escape_markdown_v2
from .profiler import profile_time

__all__ = ['escape_markdown_v2', 'profile_time'] 