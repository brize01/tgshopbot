import asyncio
import logging
import openpyxl
import os
from aiogram import Router, types
from helpers.database import async_session_maker
from helpers.message_manager import delete_previous_message
from sqlalchemy.sql import text

router = Router()
logger = logging.getLogger(__name__)

# Сохраняем данные о текущем заказе пользователя
order_sessions = {}

@router.callback_query(lambda callback_query: callback_query.data == "checkout")
async def ask_delivery_info_handler(callback_query: types.CallbackQuery):
    """
    Запрашивает у пользователя данные для доставки заказа.
    """
    user_id = callback_query.from_user.id
    logger.info(f"Пользователь `{user_id}` начал оформление заказа!")

    # Удаляем предыдущее сообщение перед запросом доставки
    await delete_previous_message(callback_query.message.bot, user_id)

    sent_message = await callback_query.message.answer("Введи данные для доставки (адрес, телефон и др.) 👇")

    # Запоминаем сообщение с запросом доставки для последующего удаления
    order_sessions[user_id] = {"message_id": sent_message.message_id}
    logger.info(f"Сохранён ID сообщения `{sent_message.message_id}` для запроса данных доставки пользователя `{user_id}`.")

@router.message(lambda message: message.from_user.id in order_sessions)
async def confirm_order_handler(message: types.Message):
    """
    Создаёт заказ и отправляет подтверждение (без оплаты через Юкасса).
    """
    user_id = message.from_user.id
    delivery_info = message.text
    logger.info(f"Получены данные доставки от `{user_id}`: {delivery_info}")

    async with async_session_maker() as session:
        # Получаем `id` пользователя
        user_query = text("SELECT id FROM users_botuser WHERE telegram_id = :user_id")
        result = await session.execute(user_query, {"user_id": user_id})
        user_db_id = result.scalar()

        if not user_db_id:
            logger.warning(f"❌ Ошибка! `telegram_id={user_id}` не найден в `users_botuser`.")
            await message.answer("❌ Ошибка! Ваш профиль не найден.")
            return

        # Создаём новый заказ
        create_order_query = text("""
        INSERT INTO shop_order (user_id, created_at, delivery_info)
        VALUES (:user_db_id, NOW(), :delivery_info)
        RETURNING id
        """)
        result = await session.execute(create_order_query, {"user_db_id": user_db_id, "delivery_info": delivery_info})
        order_id = result.scalar()
        await session.commit()

        logger.info(f"✅ Заказ `{order_id}` успешно создан для пользователя `{user_id}`.")

        # Добавляем товары в заказ
        cart_query = text("SELECT product_id, quantity FROM shop_cart WHERE user_id = :user_db_id")
        result = await session.execute(cart_query, {"user_db_id": user_db_id})
        cart_items = result.fetchall()

        total_amount = 0.0
        for product_id, quantity in cart_items:
            product_query = text("SELECT price FROM shop_product WHERE id = :product_id")
            result = await session.execute(product_query, {"product_id": product_id})
            product_price = result.scalar()

            add_order_item_query = text("""
            INSERT INTO shop_orderitem (order_id, product_id, quantity)
            VALUES (:order_id, :product_id, :quantity)
            """)
            await session.execute(add_order_item_query, {"order_id": order_id, "product_id": product_id, "quantity": quantity})
            
            total_amount += float(product_price) * quantity

        await session.commit()
        logger.info(f"Все товары из корзины добавлены в заказ `{order_id}`.")

        # Очищаем корзину пользователя
        await session.execute(text("DELETE FROM shop_cart WHERE user_id = :user_db_id"), {"user_db_id": user_db_id})
        await session.commit()
        logger.info(f"Корзина пользователя `{user_id}` успешно очищена!")

    # Удаляем предыдущее сообщение с запросом доставки
    await delete_previous_message(message.bot, user_id)
    logger.info(f"Сообщение запроса доставки пользователя `{user_id}` удалено.")

    # Клавиатура с кнопкой "🏠 Главное меню"
    menu_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="start")]
    ])

    # Подтверждение заказа
    sent_message = await message.answer(
        f"✅ Заказ №{order_id} принят!\n\n"
        f"📦 Сумма заказа: {total_amount:.2f} ₽\n"
        f"📍 Доставка: {delivery_info}\n\n"
        f"Мы свяжемся с вами для уточнения деталей!",
        reply_markup=menu_keyboard
    )
    logger.info(f"Сохранён ID сообщения `{sent_message.message_id}` для подтверждения заказа пользователя `{user_id}`.")

    # Удаляем данные из `order_sessions`
    del order_sessions[user_id]
    logger.info(f"`order_sessions[{user_id}]` Данные `order_sessions` удалены успешно!")

    # Сохраняем заказ в Excel
    async with async_session_maker() as session:
        cart_query = text("""
        SELECT shop_product.name, shop_orderitem.quantity 
        FROM shop_orderitem 
        JOIN shop_product ON shop_orderitem.product_id = shop_product.id 
        WHERE shop_orderitem.order_id = :order_id
        """)
        result = await session.execute(cart_query, {"order_id": order_id})
        cart_items = result.fetchall()

    save_order_to_excel(order_id, user_db_id, total_amount, delivery_info, cart_items)
    logger.info(f"Заказ `{order_id}` сохранён в Excel.")

def save_order_to_excel(order_id, user_id, total_amount, delivery_info, cart_items):
    """
    Сохраняет информацию о заказе в Excel-файл в папке 'orders'.
    """
    folder_path = "orders"
    file_path = os.path.join(folder_path, "orders.xlsx")

    # Проверяем, существует ли папка, если нет — создаём
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    try:
        wb = openpyxl.load_workbook(file_path)
        sheet = wb.active
    except FileNotFoundError:
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.append(["Заказ №", "Пользователь", "Сумма", "Доставка", "Товары"])

    items_str = ", ".join([f"{product_name} (x{quantity})" for product_name, quantity in cart_items])
    sheet.append([order_id, user_id, f"{total_amount:.2f} ₽", delivery_info, items_str])
    
    wb.save(file_path)
    logger.info(f"Заказ `{order_id}` сохранён в `{file_path}`.")
