"""
Утилиты для работы с Markdown форматированием.
"""

def escape_markdown_v2(text):
    """
    Экранирует специальные символы Markdown V2 в тексте.
    
    Args:
        text: Исходный текст
        
    Returns:
        str: Текст с экранированными специальными символами
    """
    if not text:
        return ""
    
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', 
                    '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    
    return text 