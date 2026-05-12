import logging
import asyncio
import nest_asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
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

async def handle_new_post_button(update, context):
    """Обрабатывает нажатие кнопки '📝 Новая публикация' где угодно."""
    context.user_data.clear()
    await start_post(update, context)

async def main():
    await init_db()
    await restore_scheduled_posts()
    scheduler.start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Кнопки из Reply-клавиатуры (обрабатываются всегда, даже если диалог не активен)
    app.add_handler(MessageHandler(filters.Regex("^📝 Новая публикация$"), handle_new_post_button))
    app.add_handler(MessageHandler(filters.Regex("^📋 Очередь$"), show_queue))
    
    # Основные обработчики
    app.add_handler(post_conversation)
    app.add_handler(CommandHandler("queue", show_queue))
    for h in admin_handlers:
        app.add_handler(h)
    app.add_handler(CommandHandler("start", start))

    logger.info("Бот запущен через polling")
    
    # Автоматический перезапуск при Conflict (если Railway не убил старый контейнер)
    while True:
        try:
            await app.run_polling(drop_pending_updates=True)
        except Conflict as e:
            logger.error(f"Conflict: {e}. Перезапуск через 5 секунд...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            break

if __name__ == "__main__":
    asyncio.run(main())
