import logging
from telegram.ext import ApplicationBuilder
from config import BOT_TOKEN
from database import init_db
from scheduler import scheduler, restore_scheduled_posts
from handlers.post import post_conversation
from handlers.admin import handlers as admin_handlers
from handlers.queue import queue_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await init_db()
    await restore_scheduled_posts()
    scheduler.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(post_conversation)
    app.add_handler(queue_handler)
    for h in admin_handlers:
        app.add_handler(h)

    logger.info("Бот запущен через polling")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
