# translations.py

# Перевод типов еды
MEAL_TYPE_TRANSLATIONS = {
    'breakfast': 'Завтрак',
    'lunch': 'Обед',
    'dinner': 'Ужин',
    '—': '—'  # Добавляем перевод для пустого значения
}

# Перевод сообщений бота
MESSAGES = {
    'welcome': 'Добро пожаловать! Что бы вы хотели сделать?',
    'choose_room': 'Выберите номер комнаты:',
    'enter_name': 'Кому готовим? Введите имя:',
    'choose_meal': 'Завтрак, обед или ужин?',
    'choose_dishes': 'Выберите блюда:',
    'no_menu': 'Меню пока недоступно. Попробуйте позже.',
    'wishes_prompt': 'Напишите пожелания к заказу текстом и отправьте,\nлибо нажмите кнопку ниже:',
    'order_added': 'Добавлено: {dish}',
    'order_removed': 'Убрано: {dish}',
    'order_created': '✅ Заказ успешно создан!\n\n📋 Ваш заказ №{order_id}:\n\n'
                    '🏠 Номер комнаты: {room}\n'
                    '👤 Имя: {name}\n'
                    '🍽 Время дня: {meal_type}\n'
                    '🍲 Блюда: {dishes}\n'
                    '📝 Пожелания: {wishes}\n'
                    '\n💰 Сумма заказа: {total} р.\n'
                    '⏰ Заказ оформлен: {timestamp}\n\n',
    'order_updated': '✅ Заказ успешно обновлён!\n\n📋 Ваш заказ №{order_id}:\n\n'
                    '🏠 Номер комнаты: {room}\n'
                    '👤 Имя: {name}\n'
                    '🍽 Время дня: {meal_type}\n'
                    '🍲 Блюда: {dishes}\n'
                    '📝 Пожелания: {wishes}\n'
                    '\n💰 Сумма заказа: {total} р.\n'
                    '⏰ Заказ оформлен: {timestamp}\n\n',
    'no_dishes': 'Выберите хотя бы одно блюдо',
    'no_wishes': '—',
    'ask_question': 'Задайте свой вопрос:',
    'question_thanks': 'Спасибо за ваш вопрос! Мы ответим вам в ближайшее время.\nЧто дальше?',
    'order_cancelled': '❌ Заказ отменён!\n\nМожете сделать новый заказ.',
    'order_cancel_error': '❌ Ошибка: заказ не найден или уже был отменён.\n\nЧто дальше?',
    'order_cancel_system_error': '❌ Произошла ошибка при отмене заказа. Попробуйте позже.\n\nЧто дальше?',
    'edit_cancelled': '✅ Редактирование отменено\n\n',
    'new_order_cancelled': 'Заказ отменен.',
    'no_active_orders': 'У вас нет активных заказов.',
    'active_orders_header': '📋 Ваши активные заказы:\n\n',
    'active_orders_separator': '➖➖➖➖➖➖➖➖➖➖\n',
    'total_sum': '\n💵 Общая сумма ваших заказов: {sum} р.',
    'what_next': '\n\nМожете сделать новый заказ.',
    'phone_request': 'Для продолжения работы, пожалуйста, поделитесь своим номером телефона.',
    'wrong_phone': 'Извините, но ваш номер телефона не найден в списке разрешенных пользователей.',
    'wrong_order_time': 'Извините, но заказы принимаются только с 10:00 до 00:00. Если у вас есть вопросы, вы можете обратиться к администратору.',
    'auth_success': 'Авторизация успешно пройдена! Теперь вы можете делать заказы.',
    'auth_failed': 'Извините, но этот номер телефона не найден в базе. Пожалуйста, попробуйте еще раз или обратитесь к администратору.',
    'auth_cancelled': 'Авторизация отменена. Используйте /start для повторной попытки.'
}

# Перевод текста кнопок
BUTTONS = {
    'new_order': '🆕 Новый заказ',
    'edit_order': '✏️ Редактировать',
    'edit_active_orders': '✏️ Редактировать активные заказы',
    'cancel_order': '❌ Отменить заказ',
    'my_orders': '📋 Мои заказы',
    'ask_question': '❓ Задать вопрос',
    'make_order': 'Сделать заказ',
    'back': '⬅️ Назад',
    'cancel': 'Отменить',
    'done': '✅ Готово',
    'no_wishes': 'Нет пожеланий',
    'breakfast': 'Завтрак',
    'lunch': 'Обед',
    'dinner': 'Ужин',
    'share_phone': '📱 Поделиться номером телефона',
    'return_to_list': '⬅️ Вернуться к списку',
    'tomorrow_menu': 'Меню на завтра',
    'back_to_menu': '⬅️ В главное меню',
    'dish_compositions': '🍴 Составы блюд',
    'back_to_menu_list': '⬅️ Назад'
}

def get_meal_type(meal_type):
    """Возвращает переведённое название типа еды."""
    return MEAL_TYPE_TRANSLATIONS.get(meal_type, meal_type)

def get_message(key, **kwargs):
    """Возвращает переведённое сообщение с подстановкой параметров."""
    message = MESSAGES.get(key, key)
    return message.format(**kwargs) if kwargs else message

def get_button(key):
    """Возвращает переведённый текст кнопки."""
    return BUTTONS.get(key, key)