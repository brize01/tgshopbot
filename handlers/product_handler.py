import logging
from aiogram import Router, types
from sqlalchemy.future import select
from sqlalchemy.sql import func
from helpers.database import get_products
from helpers.message_manager import delete_previous_message, delete_all_previous_messages, save_last_message
from helpers.database import async_session_maker
from settings.config import PRODUCTS_PER_PAGE
from helpers.models import Product

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(lambda callback_query: callback_query.data.startswith("subcategory_") or callback_query.data.startswith("product_page_"))
async def product_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    if callback_query.data.startswith("subcategory_"):
        subcategory_id = int(callback_query.data.split("_")[-1])
        page = 1
    else:
        subcategory_id, page = map(int, callback_query.data.split("_")[2:])

    logger.info(f"Пользователь {user_id} запросил товары для подкатегории {subcategory_id}, страница {page}")

    # Удаляем ВСЕ предыдущие сообщения
    await delete_all_previous_messages(callback_query.message.bot, user_id)

    # Получаем общее количество товаров в подкатегории
    total_products = await count_products_in_subcategory(subcategory_id)
    logger.info(f"В подкатегории {subcategory_id} всего товаров: {total_products}")

    # Загружаем товары для текущей страницы
    products = await get_products(subcategory_id, page)

    # Если товаров нет в подкатегории
    if not products:
        logger.warning(f"❌ В подкатегории {subcategory_id} нет товаров. Показываем кнопку '🏠 Главное меню'.")

        # Удаляем предыдущее сообщение, если оно есть
        await delete_previous_message(callback_query.message.bot, user_id)

        # Объявляем переменную sent_message
        sent_message = None

        # Создаём клавиатуру
        main_menu_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        main_menu_button = types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="start")

        main_menu_keyboard.inline_keyboard.append([main_menu_button])  # Добавляем кнопку

        logger.info(f"Отправляем кнопку '🏠 Главное меню' пользователю {user_id}")

        sent_message = await callback_query.message.answer("❌ Нет товаров в этой подкатегории.", reply_markup=main_menu_keyboard)
        
        # Сохраняем ID последнего отправленного сообщения
        await save_last_message(user_id, sent_message)
        
        return

    # Отправляем товары по одному
    for product in products:
        logger.info(f"Проверяем товар: {product.name}, цена: {product.price}, изображение: {product.image}")

        product_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
        btn = types.InlineKeyboardButton(text=f"🛒 В корзину ({product.price} ₽)", callback_data=f"add_to_cart_{product.id}")
        product_keyboard.inline_keyboard.append([btn])

        logger.info(f"Добавлена кнопка: {btn.text}")

        sent_message = await callback_query.message.answer_photo(
            photo=product.image,
            caption=f"*{product.name}*\n\n{product.description}\n\nЦена: {product.price} ₽",
            reply_markup=product_keyboard,
            parse_mode="Markdown"
        )

        await save_last_message(user_id, sent_message)  # Сохраняем ID каждого сообщения

        # Добавляем навигацию
    navigation_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Кнопка "Назад к подкатегориям"
    navigation_keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="⬅️ Назад к подкатегориям", callback_data=f"back_to_subcategories_{subcategory_id}")])
    
    # Кнопки пагинации
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"product_page_{subcategory_id}_{page - 1}"))
    
    next_page_start = page * PRODUCTS_PER_PAGE
    if next_page_start < total_products:
        pagination_buttons.append(types.InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"product_page_{subcategory_id}_{page + 1}"))
    
    if pagination_buttons:
        navigation_keyboard.inline_keyboard.append(pagination_buttons)
    # Вычисляем количество страниц
    total_pages = (total_products + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE
    navigation_text = f"Всего товаров в подкатегории: {total_products}\nСтраница {page} из {total_pages}"

    if navigation_keyboard.inline_keyboard:
        logger.info(f"Добавлены кнопки навигации.")
        sent_message = await callback_query.message.answer(navigation_text, reply_markup=navigation_keyboard)
        await save_last_message(user_id, sent_message)  # Сохраняем навигацию

    logger.info(f"Все товары успешно загружены для пользователя {user_id}")
@router.callback_query(lambda callback_query: callback_query.data.startswith("back_to_subcategories_"))
async def back_to_subcategories_handler(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки "Назад к подкатегориям".
    Возвращает к списку подкатегорий.
    """
    user_id = callback_query.from_user.id
    subcategory_id = int(callback_query.data.split("_")[-1])
    
    logger.info(f"Пользователь {user_id} возвращается к подкатегориям из подкатегории {subcategory_id}")
    
    # Получаем category_id по subcategory_id
    async with async_session_maker() as session:
        from helpers.models import SubCategory
        result = await session.execute(
            select(SubCategory).where(SubCategory.id == subcategory_id)
        )
        subcategory = result.scalar()
        
        if not subcategory:
            await callback_query.message.answer("❌ Подкатегория не найдена.")
            return
        
        category_id = subcategory.category_id
    
    # Удаляем предыдущие сообщения
    await delete_all_previous_messages(callback_query.message.bot, user_id)
    
    # Показываем подкатегории
    offset = 0
    subcategories = await get_subcategories(category_id, limit=SUBCATEGORIES_PER_PAGE, offset=offset)
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=sub.name, callback_data=f"subcategory_{sub.id}")]
        for sub in subcategories
    ])
    
    # Кнопка "Назад к категориям"
    keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="⬅️ Назад к категориям", callback_data=f"category_page_1")])
    
    sent_message = await callback_query.message.answer("Выбери подкатегорию 👇", reply_markup=keyboard)
    await save_last_message(user_id, sent_message)
async def count_products_in_subcategory(subcategory_id):
    """Возвращает общее количество товаров в подкатегории."""
    from helpers.database import async_session_maker
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count()).select_from(Product).where(Product.subcategory_id == subcategory_id)
        )
        return result.scalar()
