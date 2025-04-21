"""
Сервис для работы с платежами через API Точка банка (СБП)
"""
import os
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, Any, Tuple, List
import aiohttp

from orderbot import config

logger = logging.getLogger(__name__)

# Константы для API Точка банка
TOCHKA_BASE_URL = config.TOCHKA_BASE_URL
TOCHKA_API_TOKEN = config.TOCHKA_API_TOKEN
TOCHKA_CUSTOMER_CODE = config.TOCHKA_CUSTOMER_CODE
SBP_API_VERSION = 'v1.0'


class TochkaSBPClient:
    """Клиент для работы с API СБП от Точка банка."""

    def __init__(self) -> None:
        """Инициализирует клиент API Точка банка."""
        self.base_url = TOCHKA_BASE_URL
        self.api_token = TOCHKA_API_TOKEN
        self.customer_code = TOCHKA_CUSTOMER_CODE
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        if not self.api_token or not self.customer_code:
            logger.warning(
                "Не настроены переменные окружения для API Точка банка. "
                "Платежи через СБП будут недоступны."
            )
    
    async def _make_request(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Выполняет запрос к API Точка банка.
        
        Args:
            method: HTTP метод (GET, POST, etc.)
            endpoint: Конечная точка API
            data: Данные для запроса (для POST, PUT)
            
        Returns:
            Dict[str, Any]: Ответ от API в формате JSON
            
        Raises:
            Exception: При ошибке запроса
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == "GET":
                    async with session.get(url, headers=self.headers) as response:
                        response_data = await response.json()
                        if response.status != 200:
                            logger.error(f"Ошибка API Точка: {response.status}, {response_data}")
                            raise Exception(f"Ошибка API Точка: {response.status}, {response_data}")
                        return response_data
                
                elif method.upper() == "POST":
                    async with session.post(url, headers=self.headers, json=data) as response:
                        response_data = await response.json()
                        if response.status not in (200, 201):
                            logger.error(f"Ошибка API Точка: {response.status}, {response_data}")
                            raise Exception(f"Ошибка API Точка: {response.status}, {response_data}")
                        return response_data
                
                else:
                    raise ValueError(f"Неподдерживаемый HTTP метод: {method}")
        
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка соединения с API Точка: {e}")
            raise Exception(f"Не удалось подключиться к API Точка: {e}")
    
    async def create_qr_code(
        self, amount: float, order_id: str, description: str
    ) -> Dict[str, Any]:
        """
        Создает QR-код для оплаты через СБП.
        
        Args:
            amount: Сумма платежа
            order_id: Идентификатор заказа
            description: Описание платежа
            
        Returns:
            Dict[str, Any]: Информация о созданном QR-коде
            
        Raises:
            Exception: При ошибке создания QR-кода
        """
        # Проверяем, настроено ли API
        if not self.api_token or not self.customer_code:
            raise Exception("API Точка банка не настроено. Платежи через СБП недоступны.")
        
        # Формируем уникальный идентификатор QR-кода
        qrc_id = f"ECOCAMP_{uuid.uuid4().hex[:16]}"
        
        # Формируем запрос согласно документации API Точка банка
        # Для создания QR-кода используем метод Register Qr Code
        request_data = {
            "Data": {
                "qrcType": "02",  # 02 - Динамический QR-код
                "amount": int(amount * 100),  # Сумма в копейках
                "currency": "RUB",
                "paymentPurpose": description,
                "sourceName": "ECOCAMP_BOT",
                "qrcId": qrc_id,
                "additionalInfo": order_id
            }
        }
        
        # В соответствии с документацией API, структура URL:
        # /sbp/{apiVersion}/qr-code/merchant/{merchantId}/{accountId}
        # Мы используем customerCode вместо merchantId и accountId
        endpoint = f"sbp/{SBP_API_VERSION}/qr-code/merchant/{self.customer_code}/{self.customer_code}"
        
        try:
            logger.info(f"Отправляем запрос на создание QR-кода: {endpoint}, данные: {request_data}")
            result = await self._make_request("POST", endpoint, request_data)
            
            if result and "Data" in result:
                qr_data = result["Data"]
                logger.info(f"Создан QR-код для оплаты: {qr_data}")
                
                # Преобразуем ответ в формат, ожидаемый нашим приложением
                return {
                    "qrcId": qrc_id,
                    "payload": qr_data.get("payload", ""),
                    "amount": amount,
                    "description": description
                }
            
            raise Exception(f"Неожиданный ответ от API Точка: {result}")
        
        except Exception as e:
            logger.error(f"Ошибка при создании QR-кода: {e}")
            raise Exception(f"Не удалось создать QR-код для оплаты: {e}")
    
    async def get_payment_status(self, qrc_id: str) -> Dict[str, Any]:
        """
        Получает статус платежа по идентификатору QR-кода.
        
        Args:
            qrc_id: Идентификатор QR-кода
            
        Returns:
            Dict[str, Any]: Информация о статусе платежа
            
        Raises:
            Exception: При ошибке получения статуса
        """
        if not self.api_token or not self.customer_code:
            raise Exception("API Точка банка не настроено. Проверка статуса платежа недоступна.")
        
        # Согласно документации, запрос статуса QR-кода:
        # GET /sbp/{apiVersion}/qr-code/legal-entity/{legalId}
        endpoint = f"sbp/{SBP_API_VERSION}/qr-code/legal-entity/{self.customer_code}"
        
        try:
            result = await self._make_request("GET", endpoint)
            
            if not result or "Data" not in result or "qrCodeList" not in result["Data"]:
                return {"status": "NotFound", "message": "Платеж не найден"}
            
            # Ищем QR-код по ID
            qr_codes = result["Data"]["qrCodeList"]
            for qr_code in qr_codes:
                if qr_code.get("qrcId") == qrc_id:
                    return {
                        "status": qr_code.get("status", "Unknown"),
                        "message": "QR-код найден",
                        "qrcId": qrc_id,
                        "amount": qr_code.get("amount", 0)
                    }
            
            return {"status": "NotFound", "message": "Платеж не найден"}
        
        except Exception as e:
            logger.error(f"Ошибка при получении статуса платежа: {e}")
            raise Exception(f"Не удалось получить статус платежа: {e}")
    
    async def get_all_payments(
        self, from_date: Optional[str] = None, to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает список всех платежей за период.
        
        Args:
            from_date: Начальная дата в формате YYYY-MM-DD
            to_date: Конечная дата в формате YYYY-MM-DD
            
        Returns:
            List[Dict[str, Any]]: Список платежей
            
        Raises:
            Exception: При ошибке получения списка платежей
        """
        if not self.api_token or not self.customer_code:
            raise Exception("API Точка банка не настроено. Получение списка платежей недоступно.")
        
        # Согласно документации, получение списка QR-кодов:
        # GET /sbp/{apiVersion}/qr-code/legal-entity/{legalId}
        endpoint = f"sbp/{SBP_API_VERSION}/qr-code/legal-entity/{self.customer_code}"
        
        try:
            result = await self._make_request("GET", endpoint)
            
            if not result or "Data" not in result or "qrCodeList" not in result["Data"]:
                return []
            
            return result["Data"]["qrCodeList"]
        
        except Exception as e:
            logger.error(f"Ошибка при получении списка платежей: {e}")
            raise Exception(f"Не удалось получить список платежей: {e}")


# Создаем экземпляр клиента для использования в других модулях
tochka_client = TochkaSBPClient() 