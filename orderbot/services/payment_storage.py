from typing import Dict, Optional, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Словарь для хранения активных платежей
# Ключ - chat_id, значение - словарь с данными платежа
active_payments: Dict[int, Dict[str, Any]] = {}

def store_payment(chat_id: int, payment_data: Dict[str, Any]) -> None:
    """
    Сохраняет данные платежа для указанного чата
    
    Args:
        chat_id: ID чата
        payment_data: Данные платежа
    """
    active_payments[chat_id] = {
        **payment_data,
        'created_at': datetime.now().isoformat()
    }
    logger.info(f"Сохранены данные платежа для chat_id={chat_id}")

def get_payment(chat_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает данные платежа для указанного чата
    
    Args:
        chat_id: ID чата
        
    Returns:
        Optional[Dict[str, Any]]: Данные платежа или None, если платеж не найден
    """
    return active_payments.get(chat_id)

def remove_payment(chat_id: int) -> None:
    """
    Удаляет данные платежа для указанного чата
    
    Args:
        chat_id: ID чата
    """
    if chat_id in active_payments:
        del active_payments[chat_id]
        logger.info(f"Удалены данные платежа для chat_id={chat_id}")

def update_payment_message_ids(chat_id: int, qr_message_id: Optional[int] = None, buttons_message_id: Optional[int] = None) -> None:
    """
    Обновляет ID сообщений для платежа
    
    Args:
        chat_id: ID чата
        qr_message_id: ID сообщения с QR-кодом
        buttons_message_id: ID сообщения с кнопками
    """
    if chat_id in active_payments:
        if qr_message_id is not None:
            active_payments[chat_id]['qr_message_id'] = qr_message_id
        if buttons_message_id is not None:
            active_payments[chat_id]['buttons_message_id'] = buttons_message_id
        logger.info(f"Обновлены ID сообщений для chat_id={chat_id}") 