import logging
from aiogram import Router, types
from aiogram.filters import Command
from helpers.database import get_questions
from helpers.message_manager import delete_previous_message, save_last_message

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(lambda callback_query: callback_query.data == "faq")
async def faq_handler(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки FAQ.
    Загружает вопросы из БД и показывает их пользователю.
    """
    user_id = callback_query.from_user.id
    logger.info(f"Обработчик FAQ вызван пользователем {user_id}")

    # Удаляем предыдущее сообщение, если оно есть
    await delete_previous_message(callback_query.message.bot, user_id)

    # Объявляем переменную sent_message
    sent_message = None  

    questions = await get_questions()
    logger.info(f"Загружено {len(questions)} вопросов из БД")

    if not questions:
        logger.warning("База данных пустая! Отправляем сообщение о пустом FAQ.")
        sent_message = await callback_query.message.answer("❗ В базе данных пока нет вопросов и ответов!")
    else:
        # Создаём клавиатуру с вопросами
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=q.text, callback_data=f"faq_answer_{q.id}")]
            for q in questions
        ])
        
        # Добавляем кнопку "🏠 Главное меню"
        keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="start")])
        
        sent_message = await callback_query.message.answer(
            "❓ **Часто задаваемые вопросы**:\n\nВыберите вопрос, чтобы увидеть ответ:",
            reply_markup=keyboard
        )

    # Сохраняем ID последнего отправленного сообщения
    await save_last_message(user_id, sent_message)

    logger.info(f"Отправлено сообщение с FAQ пользователю {user_id}")

@router.callback_query(lambda callback_query: callback_query.data.startswith("faq_answer_"))
async def faq_answer_handler(callback_query: types.CallbackQuery):
    """
    Обработчик кнопки с вопросом FAQ.
    Показывает ответ на выбранный вопрос.
    """
    user_id = callback_query.from_user.id
    question_id = int(callback_query.data.split("_")[-1])
    logger.info(f"Пользователь {user_id} выбрал вопрос {question_id}")

    # Удаляем предыдущее сообщение, если оно есть
    await delete_previous_message(callback_query.message.bot, user_id)

    # Объявляем переменную sent_message
    sent_message = None  

    questions = await get_questions()
    question = next((q for q in questions if q.id == question_id), None)

    if not question:
        sent_message = await callback_query.message.answer("❌ Вопрос не найден.")
    else:
        # Клавиатура с кнопкой возврата к FAQ
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="❓ Назад к FAQ", callback_data="faq")],
            [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="start")]
        ])
        
        sent_message = await callback_query.message.answer(
            f"❓ **{question.text}**\n\n{question.answer}",
            reply_markup=keyboard
        )

    # Сохраняем ID последнего отправленного сообщения
    await save_last_message(user_id, sent_message)

    logger.info(f"Отправлен ответ на вопрос {question_id} пользователю {user_id}")

@router.message(Command("faq"))
async def faq_command_handler(message: types.Message):
    """
    Обработчик команды /faq.
    Показывает список вопросов FAQ.
    """
    user_id = message.from_user.id

    # Удаляем предыдущее сообщение, если оно есть
    await delete_previous_message(message.bot, user_id)

    # Объявляем переменную sent_message
    sent_message = None  

    questions = await get_questions()
    logger.info(f"Загружено {len(questions)} вопросов из БД")

    if not questions:
        sent_message = await message.answer("❗ В базе данных пока нет вопросов и ответов!")
    else:
        # Создаём клавиатуру с вопросами
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text=q.text, callback_data=f"faq_answer_{q.id}")]
            for q in questions
        ])
        
        # Добавляем кнопку "🏠 Главное меню"
        keyboard.inline_keyboard.append([types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="start")])
        
        sent_message = await message.answer(
            "❓ **Часто задаваемые вопросы**:\n\nВыберите вопрос, чтобы увидеть ответ:",
            reply_markup=keyboard
        )

    # Сохраняем ID последнего отправленного сообщения
    await save_last_message(user_id, sent_message)

    logger.info(f"Отправлено сообщение с FAQ пользователю {user_id}")
