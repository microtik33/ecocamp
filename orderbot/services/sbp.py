import requests
import json
import logging
from typing import Dict, Optional, Any, List, Tuple, Union
from datetime import datetime

from ..config import TOCHKA_JWT_TOKEN, TOCHKA_CLIENT_ID

# Базовый URL для API Точки (исправлен в соответствии с документацией)
BASE_URL = 'https://enter.tochka.com/uapi'
API_VERSION = 'v1.0'

# Настройка логгера
logger = logging.getLogger(__name__)

def _get_headers() -> Dict[str, str]:
    """
    Возвращает заголовки для запросов к API Точки
    
    Returns:
        Dict[str, str]: Заголовки для запроса
    """
    if not TOCHKA_JWT_TOKEN:
        logger.error("JWT токен не найден в переменных окружения!")
        return {}
        
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
        url = f"{BASE_URL}/sbp/{API_VERSION}/customer/info"
        headers = _get_headers()
        
        if not headers:
            return {"error": "JWT токен не настроен"}
            
        logger.info(f"Отправка запроса на {url}")
        response = requests.get(url, headers=headers)
        logger.info(f"Получен ответ: статус {response.status_code}")
        
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
        account_id: Идентификатор счета в формате "номер_счета/БИК"
        merchant_id: Идентификатор торговой точки
        amount: Сумма платежа в копейках
        payment_purpose: Назначение платежа
        
    Returns:
        Dict[str, Any]: Данные созданного QR-кода
    """
    try:
        # Проверка наличия обязательных параметров
        if not account_id or not merchant_id:
            logger.error(f"Не указаны обязательные параметры: account_id={account_id}, merchant_id={merchant_id}")
            return {"error": "Не указаны обязательные параметры"}
        
        # Проверка формата account_id (должен быть в формате "номер_счета/БИК")
        if "/" not in account_id:
            logger.error(f"Неверный формат account_id: {account_id}. Должен быть в формате 'номер_счета/БИК'")
            return {"error": "Неверный формат идентификатора счета"}
            
        # Формирование URL запроса в соответствии с документацией
        url = f"{BASE_URL}/sbp/{API_VERSION}/qr-code/merchant/{merchant_id}/{account_id}"
        
        # Заголовки запроса
        headers = _get_headers()
        if not headers:
            return {"error": "JWT токен не настроен"}
        
        # Формирование тела запроса в соответствии с документацией
        data = {
            "Data": {
                "amount": amount,
                "currency": "RUB",
                "paymentPurpose": payment_purpose,
                "qrcType": "02",  # Динамический QR-код
                "imageParams": {
                    "width": 300,
                    "height": 300,
                    "mediaType": "image/png"
                },
                "sourceName": "EcoCamp Bot",
                "ttl": 30  # Время жизни QR-кода - 30 минут
            }
        }
        
        logger.info(f"Отправка запроса на регистрацию QR-кода: URL={url}")
        logger.info(f"Тело запроса: {json.dumps(data)}")
        
        response = requests.post(url, headers=headers, json=data)
        
        logger.info(f"Получен ответ: статус {response.status_code}")
        if response.status_code != 200:
            logger.error(f"Ошибка ответа: {response.text}")
            
        response.raise_for_status()
        response_data = response.json()
        
        # Проверка структуры ответа
        if 'Data' not in response_data:
            logger.error(f"Неожиданный формат ответа: {response_data}")
            return {"error": "Неожиданный формат ответа"}
            
        return response_data['Data']
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
        # Формирование URL запроса в соответствии с документацией
        url = f"{BASE_URL}/sbp/{API_VERSION}/qr-codes/{qrc_id}/payment-status"
        
        headers = _get_headers()
        if not headers:
            return {"error": "JWT токен не настроен"}
            
        logger.info(f"Отправка запроса на получение статуса: URL={url}")
        
        response = requests.get(url, headers=headers)
        
        logger.info(f"Получен ответ: статус {response.status_code}")
        
        if response.status_code != 200:
            logger.error(f"Ошибка ответа: {response.text}")
            return {"error": f"Ошибка API: {response.status_code}", "message": response.text}
            
        response.raise_for_status()
        response_data = response.json()
        
        # Подробное логирование ответа для отладки
        logger.info(f"Полный ответ API: {json.dumps(response_data, ensure_ascii=False)}")
        
        # Проверка структуры ответа
        if 'Data' not in response_data:
            logger.error(f"Отсутствует ключ 'Data' в ответе: {response_data}")
            return {"error": "Неожиданный формат ответа: отсутствует ключ 'Data'"}
            
        if 'paymentList' not in response_data['Data']:
            logger.error(f"Отсутствует ключ 'paymentList' в Data: {response_data['Data']}")
            return {"error": "Неожиданный формат ответа: отсутствует ключ 'paymentList'"}
            
        # Получаем статус из первого элемента списка платежей
        payment_list = response_data['Data']['paymentList']
        
        if not payment_list:
            logger.warning(f"Список платежей пуст для QR-кода {qrc_id}")
            return {"status": "unknown", "message": "Платеж не найден"}
            
        if len(payment_list) > 0:
            payment = payment_list[0]
            logger.info(f"Информация о платеже: {json.dumps(payment, ensure_ascii=False)}")
            return payment
        else:
            logger.warning(f"Список платежей пуст для QR-кода {qrc_id}")
            return {"status": "unknown", "message": "Платеж не найден"}
    except Exception as e:
        logger.error(f"Ошибка при получении статуса QR-кода: {e}")
        return {"error": str(e), "message": "Ошибка при обработке запроса"} 