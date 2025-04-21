import requests
import json
import logging
from typing import Dict, Optional, Any, List, Tuple, Union
from datetime import datetime

from ..config import TOCHKA_JWT_TOKEN, TOCHKA_CLIENT_ID

# Базовый URL для API Точки
BASE_URL = 'https://enter.tochka.com/api/v2'

# Настройка логгера
logger = logging.getLogger(__name__)

def _get_headers() -> Dict[str, str]:
    """
    Возвращает заголовки для запросов к API Точки
    
    Returns:
        Dict[str, str]: Заголовки для запроса
    """
    return {
        'Authorization': f'Bearer {TOCHKA_JWT_TOKEN}',
        'Content-Type': 'application/json'
    }

def get_customer_info() -> Dict[str, Any]:
    """
    Получает информацию о клиенте и его регистрации в СБП
    
    Returns:
        Dict[str, Any]: Информация о клиенте
    """
    try:
        url = f"{BASE_URL}/sbp/customer/info"
        response = requests.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при получении информации о клиенте: {e}")
        return {}

def register_qr_code(account_id: str, merchant_id: str, amount: int, 
                    payment_purpose: str = "Оплата заказа в EcoCamp") -> Dict[str, Any]:
    """
    Регистрирует динамический QR-код для оплаты
    
    Args:
        account_id: Идентификатор счета
        merchant_id: Идентификатор торговой точки
        amount: Сумма платежа в копейках
        payment_purpose: Назначение платежа
        
    Returns:
        Dict[str, Any]: Данные созданного QR-кода
    """
    try:
        url = f"{BASE_URL}/sbp/qr-code/register"
        data = {
            "accountId": account_id,
            "merchantId": merchant_id,
            "paymentPurpose": payment_purpose,
            "amount": amount,
            "qrcType": "02",  # Динамический QR-код
            "ttl": 30,  # Время жизни QR-кода - 30 минут
            "sourceName": "EcoCamp Bot",
            "imageParams": {
                "width": 300,
                "height": 300
            }
        }
        
        response = requests.post(url, headers=_get_headers(), json=data)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при создании QR-кода: {e}")
        return {}

def get_qr_code_status(qrc_id: str) -> Dict[str, Any]:
    """
    Проверяет статус оплаты QR-кода
    
    Args:
        qrc_id: Идентификатор QR-кода
        
    Returns:
        Dict[str, Any]: Статус QR-кода
    """
    try:
        url = f"{BASE_URL}/sbp/qr-code/payment-status"
        params = {
            "qrcId": qrc_id
        }
        
        response = requests.get(url, headers=_get_headers(), params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Ошибка при получении статуса QR-кода: {e}")
        return {} 