import logging
import nest_asyncio
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    PicklePersistence, PersistenceInput
)
from telegram import Update
from telegram.error import Conflict

from config import BOT_TOKEN
from database import init_db
from scheduler import scheduler, restore_scheduled_posts
from handlers.post import post_conversation, start_post
from handlers.admin import handlers as admin_handlers
from handlers.queue import show_queue
from handlers.start import start

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Логирование всех входящих обновлений — поможет увидеть, приходят ли callback
async def debug_log(update: Update, context):
    logger.info(f"Получено обновление: {update.to_dict()}")
    return  # пустой хендлер, можно добавить в самое начало

async def handle_new_post_button(update, context):
    context.user_data.clear()
    await start_post(update, context)

async def main():
    await init_db()
    await restore_scheduled_posts()
    scheduler.start()

    persistence = PicklePersistence(
        filepath="/data/bot_persistence.pkl",
        store_data=PersistenceInput(bot_data=False, chat_data=True, user_data=True, callback_data=False)
    )

    app = ApplicationBuilder() \
        .token(BOT_TOKEN) \
        .persistence(persistence) \
        .build()

    # Первым ставим отладочный хендлер — увидим абсолютно все события
    app.add_handler(MessageHandler(filters.ALL, debug_log), group=-1)
    app.add_handler(CallbackQueryHandler(debug_log, pattern=r".*"), group=-1)

    # Рабочие хендлеры
    app.add_handler(MessageHandler(filters.Regex("^📝 Новая публикация$"), handle_new_post_button))
    app.add_handler(MessageHandler(filters.Regex("^📋 Очередь$"), show_queue))
    app.add_handler(post_conversation)
    app.add_handler(CommandHandler("queue", show_queue))
    for h in admin_handlers:
        app.add_handler(h)
    app.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен через polling")
    try:
        await app.run_polling(drop_pending_updates=True)
    except Conflict:
        logger.critical("Обнаружен второй экземпляр бота. Завершаю работу.")
        raise SystemExit(1)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
