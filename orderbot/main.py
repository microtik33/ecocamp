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
from .handlers.menu import start, show_tomorrow_menu, show_dish_compositions, back_to_main_menu, show_today_menu, update_caches
from .handlers.order import (
    PHONE, MENU, ROOM, NAME, MEAL_TYPE, 
    DISH_SELECTION, WISHES, QUESTION,
    ask_room,
    show_user_orders,
    cancel_order,
    ask_name,
    handle_order_update,
    ask_meal_type,
    show_dishes,
    handle_dish_selection,
    handle_text_input,
    handle_order_time_error,
    show_edit_active_orders,
    start_new_order
)
from .handlers.states import PAYMENT
from .handlers import handle_question, save_question, ask_command
from .handlers.auth import start as auth_start, handle_phone, setup_commands_for_user
from .handlers.kitchen import kitchen_summary, search_orders_by_room, search_orders_by_number, find_orders_by_room, back_to_kitchen, handle_order_number_input
from .handlers.stats import performance_stats, clear_performance_stats, memory_stats, function_stats
from .handlers.payment import create_payment, check_payment_status, cancel_payment
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
from .services.sheets import auth_sheet, is_user_cook, force_update_menu_cache, force_update_composition_cache, force_update_today_menu_cache

# Включаем tracemalloc для диагностики
tracemalloc.start()

# Устанавливаем часовой пояс для Москвы
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
os.environ['TZ'] = 'Europe/Moscow'

# Глобальная переменная для отслеживания доступности job_queue
HAVE_JOB_QUEUE = False

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
    # Инициализация приложения с явным включением JobQueue
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    try:
        await application.initialize()
        
        # Проверяем, можно ли использовать job_queue, но не пытаемся создать его вручную,
        # если он не поддерживается
        global HAVE_JOB_QUEUE
        HAVE_JOB_QUEUE = True
        
        if application.job_queue is None:
            logging.warning("JobQueue не инициализирован. Автоматическая проверка статуса платежей будет недоступна.")
            logging.warning("Для включения JobQueue установите: pip install \"python-telegram-bot[job-queue]\"")
            HAVE_JOB_QUEUE = False
            # Не пытаемся создать его вручную, так как это вызовет ошибку

        # Запускаем задачу обновления статусов заказов
        start_status_update_task()
        
        # Запускаем задачу поддержания активности
        keep_alive_task = asyncio.create_task(keep_alive())

        # Принудительно обновляем кэш меню и составов при запуске
        try:
            logging.info("Обновление кэшей при запуске бота")
            await force_update_menu_cache()
            await force_update_composition_cache()
            await force_update_today_menu_cache()
            logging.info("Все кэши успешно обновлены при запуске")
        except Exception as e:
            logging.error(f"Ошибка при обновлении кэшей при запуске: {e}")

        # Добавляем обработчик команды /kitchen для повара
        application.add_handler(CommandHandler('kitchen', kitchen_summary))
        
        # Добавляем обработчики для поиска заказов
        application.add_handler(CallbackQueryHandler(search_orders_by_room, pattern="search_by_room"))
        application.add_handler(CallbackQueryHandler(search_orders_by_number, pattern="search_by_number"))
        application.add_handler(CallbackQueryHandler(find_orders_by_room, pattern="^find_room:[0-9]+$"))
        application.add_handler(CallbackQueryHandler(back_to_kitchen, pattern="back_to_kitchen"))
        
        # Добавляем обработчик для текстового ввода номера заказа
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(r'^\/.*') & filters.Regex(r'^\d+$'),
            handle_order_number_input
        ), group=1)
        
        # Добавляем обработчик команды /today для просмотра меню на сегодня
        application.add_handler(CommandHandler('today', show_today_menu))
        
        # Добавляем обработчик команды /update для обновления кэшей меню (только для поваров)
        application.add_handler(CommandHandler('update', update_caches))
        
        # Добавляем обработчики команд статистики
        application.add_handler(CommandHandler('stats', performance_stats))
        application.add_handler(CommandHandler('clearstats', clear_performance_stats))
        application.add_handler(CommandHandler('memory', memory_stats))
        application.add_handler(CommandHandler('funcstats', function_stats))
        
        # Устанавливаем базовые команды для всех пользователей
        await setup_commands_for_user(application.bot)
        
        # Настраиваем обработчик для проверки пользователя после авторизации
        async def post_auth_command_setup(update: Update, context):
            user_id = update.effective_user.id
            is_cook = is_user_cook(str(user_id))
            await setup_commands_for_user(context.bot, user_id, is_cook)
            return None
            
        # Добавляем обработчик для настройки команд после авторизации
        application.add_handler(
            MessageHandler(filters.Regex(r'.*Авторизация успешна.*'), post_auth_command_setup),
            group=999
        )
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler('start', auth_start),
                CommandHandler('myorders', show_user_orders),
                CommandHandler('new', start_new_order),
                CommandHandler('menu', show_tomorrow_menu),
                CommandHandler('today', show_today_menu),
                CommandHandler('ask', ask_command)
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
                    CallbackQueryHandler(back_to_main_menu, pattern='back_to_menu'),
                    CallbackQueryHandler(create_payment, pattern='pay_orders')
                ],
                ROOM: [
                    CallbackQueryHandler(ask_name, pattern='^room:([1-9]|1[0-9]|20)$'),
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
                ],
                PAYMENT: [
                    CallbackQueryHandler(check_payment_status, pattern='check_payment'),
                    CallbackQueryHandler(cancel_payment, pattern='cancel_payment')
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