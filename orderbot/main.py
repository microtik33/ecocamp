# Импортируем config первым для инициализации логирования
from . import config

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram import Update
from .handlers.menu import start, show_tomorrow_menu, show_dish_compositions, back_to_main_menu
from .handlers.order import (
    PHONE, MENU, ROOM, NAME, MEAL_TYPE, 
    DISH_SELECTION, WISHES, QUESTION,
    ask_room,
    show_user_orders,
    handle_question,
    cancel_order,
    ask_name,
    handle_order_update,
    ask_meal_type,
    show_dishes,
    handle_dish_selection,
    handle_text_input,
    save_question,
    handle_order_time_error,
    show_edit_active_orders,
    start_new_order
)
from .handlers.auth import start as auth_start, handle_phone
from .handlers.kitchen import kitchen_summary
from .tasks import start_status_update_task, stop_status_update_task, schedule_daily_tasks
import os
import asyncio
import sys
import tracemalloc
import logging
from aiohttp import web, ClientSession
from datetime import datetime
import pytz
from .services.records import process_daily_orders
from .services.sheets import auth_sheet

# Включаем tracemalloc для диагностики
tracemalloc.start()

# Устанавливаем часовой пояс для Москвы
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
os.environ['TZ'] = 'Europe/Moscow'

async def keep_alive():
    """Поддерживает сервис активным, выполняя HTTP-запросы каждые 10 минут."""
    webhook_url = os.getenv('RENDER_EXTERNAL_URL')
    if not webhook_url:
        return

    async with ClientSession() as session:
        while True:
            try:
                async with session.get(webhook_url) as response:
                    logging.info(f"Ping response: {response.status}")
                await asyncio.sleep(600)  # Ждем 10 минут
            except Exception as e:
                logging.error(f"Ошибка в keep_alive: {e}")
                await asyncio.sleep(60)  # При ошибке ждем 1 минуту перед повторной попыткой

async def main() -> None:
    """Запуск бота."""
    # Инициализация приложения
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    try:
        await application.initialize()

        # Запускаем задачу обновления статусов заказов
        start_status_update_task()
        
        # Запускаем задачу поддержания активности
        keep_alive_task = asyncio.create_task(keep_alive())

        # Добавляем обработчик команды /kitchen для повара
        application.add_handler(CommandHandler('kitchen', kitchen_summary))
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', auth_start),
                CommandHandler('myorders', show_user_orders),
                CommandHandler('new', start_new_order),
                CommandHandler('menu', show_tomorrow_menu)
            ],
            states={
                PHONE: [
                    MessageHandler(filters.CONTACT, handle_phone)
                ],
                MENU: [
                    CallbackQueryHandler(ask_room, pattern='new_order'),
                    CallbackQueryHandler(handle_order_update, pattern='edit_order'),
                    CallbackQueryHandler(show_user_orders, pattern='my_orders'),
                    CallbackQueryHandler(handle_question, pattern='question'),
                    CallbackQueryHandler(cancel_order, pattern='cancel_order'),
                    CallbackQueryHandler(handle_order_time_error, pattern='order_time_error'),
                    CallbackQueryHandler(show_edit_active_orders, pattern='edit_active_orders'),
                    CallbackQueryHandler(show_tomorrow_menu, pattern='tomorrow_menu'),
                    CallbackQueryHandler(show_dish_compositions, pattern='show_compositions'),
                    CallbackQueryHandler(back_to_main_menu, pattern='back_to_menu')
                ],
                ROOM: [
                    CallbackQueryHandler(ask_name, pattern='^room:[1-6]$'),
                    CallbackQueryHandler(handle_order_update, pattern='cancel')
                ],
                NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, ask_meal_type),
                    CallbackQueryHandler(handle_order_update, pattern='cancel'),
                    CallbackQueryHandler(handle_order_update, pattern='back')
                ],
                MEAL_TYPE: [
                    CallbackQueryHandler(show_dishes, pattern='^meal:(breakfast|lunch|dinner)$'),
                    CallbackQueryHandler(handle_order_update, pattern='cancel'),
                    CallbackQueryHandler(handle_order_update, pattern='back')
                ],
                DISH_SELECTION: [
                    CallbackQueryHandler(handle_dish_selection, pattern='^done$'),
                    CallbackQueryHandler(handle_dish_selection, pattern='^add_dish:'),
                    CallbackQueryHandler(handle_dish_selection, pattern='^remove_dish:'),
                    CallbackQueryHandler(handle_dish_selection, pattern='^select_dish:'),
                    CallbackQueryHandler(handle_dish_selection, pattern='^quantity:'),
                    CallbackQueryHandler(handle_order_update, pattern='cancel'),
                    CallbackQueryHandler(handle_order_update, pattern='back')
                ],
                WISHES: [
                    CallbackQueryHandler(handle_order_update),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input)
                ],
                QUESTION: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, save_question)
                ]
            },
            fallbacks=[CommandHandler('start', auth_start)],
            allow_reentry=True,
            per_message=False
        )

        application.add_handler(conv_handler)
        
        # Добавляем глобальные обработчики для кнопок, 
        # чтобы они работали даже если пользователь не в активном диалоге
        application.add_handler(CallbackQueryHandler(show_tomorrow_menu, pattern='tomorrow_menu'))
        application.add_handler(CallbackQueryHandler(show_dish_compositions, pattern='show_compositions'))
        application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern='back_to_menu'))
        
        # Запуск планировщика задач
        asyncio.create_task(schedule_daily_tasks())
        
        # Обработка заказов за текущий день при старте
        await process_daily_orders()
        
        # Запуск бота в соответствующем режиме
        webhook_url = os.getenv('RENDER_EXTERNAL_URL')
        if webhook_url:
            port = int(os.getenv('PORT', 10000))
            secret_token = os.getenv('WEBHOOK_SECRET', 'your-secret-token')
            webhook_path = '/webhook'
            
            # Настройка вебхука
            await application.bot.set_webhook(
                url=f"{webhook_url}{webhook_path}",
                secret_token=secret_token
            )
            
            # Создаем aiohttp веб-приложение
            app = web.Application()
            
            # Добавляем маршрут для вебхука
            async def handle_webhook(request):
                if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != secret_token:
                    return web.Response(status=403)
                    
                data = await request.json()
                await application.update_queue.put(Update.de_json(data, application.bot))
                return web.Response()
                
            app.router.add_post(webhook_path, handle_webhook)
            
            # Добавляем маршрут для пинга
            async def handle_ping(request):
                return web.Response(text="OK")
            
            app.router.add_get('/', handle_ping)
            
            # Запускаем приложение
            logging.info(f"Запуск вебхука на порту {port}")
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', port)
            await site.start()
            
            # Запускаем бота
            await application.start()
            
            # Ждем forever
            await asyncio.Event().wait()
        else:
            logging.info("Запуск бота в режиме поллинга...")
            await application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logging.error(f"Произошла ошибка: {e}")
        sys.exit(1)
    finally:
        stop_status_update_task()
        await application.shutdown()

def main_sync():
    """Синхронная обертка для запуска асинхронного main()"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен пользователем")
        sys.exit(0)

if __name__ == '__main__':
    main_sync() 