import logging
import nest_asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    PicklePersistence,
    PersistenceInput,
)

from config import BOT_TOKEN
from database import init_db
from scheduler import scheduler, restore_scheduled_posts
from handlers.post import post_conversation
from handlers.admin import handlers as admin_handlers
from handlers.queue import show_queue
from handlers.start import start

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_queue_button(update, context):
    """Кнопка '📋 Очередь'."""
    await show_queue(update, context)


async def main():
    await init_db()
    await restore_scheduled_posts()
    scheduler.start()

    persistence = PicklePersistence(
        filepath="/data/bot_persistence.pkl",
        store_data=PersistenceInput(
            bot_data=False, chat_data=True, user_data=True, callback_data=False
        ),
    )

    app = ApplicationBuilder().token(BOT_TOKEN).persistence(persistence).build()

    # Кнопка "Очередь" (отдельно, чтобы работала всегда)
    app.add_handler(MessageHandler(filters.Regex("^📋 Очередь$"), handle_queue_button))
    # Основной диалог создания поста (включает обработку кнопки "Новая публикация")
    app.add_handler(post_conversation)
    # Команды
    app.add_handler(CommandHandler("queue", show_queue))
    for h in admin_handlers:
        app.add_handler(h)
    app.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен через polling")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
