from telegram.ext import MessageHandler, filters

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📝 Создать пост":
        # Перенаправляем в тот же ConversationHandler
        return await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Запускаю создание поста...",
            reply_markup=None
        )
        # и потом сразу /post, но лучше использовать `context.dispatcher.update_queue`
        # Проще: отправить сообщение и затем имитировать команду /post через run_async
        # Но надёжнее просто вызвать start_post напрямую, передав update с text="/post"
        update.message.text = "/post"
        await context.application.process_update(update)
    elif text == "📋 Очередь":
        update.message.text = "/queue"
        await context.application.process_update(update)

# Регистрируем в bot.py:
from handlers.start import handle_main_buttons
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_buttons))
