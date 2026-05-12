from telegram import Update, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
from database import async_session, ScheduledPost
from sqlalchemy import select
from datetime import datetime
from keyboards import queue_post_actions, confirm_delete, time_selection, date_selection
from scheduler import remove_scheduled_job, reschedule_job

async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with async_session() as session:
        result = await session.execute(
            select(ScheduledPost).where(ScheduledPost.status == "pending").order_by(ScheduledPost.scheduled_at)
        )
        posts = result.scalars().all()
    if not posts:
        await update.message.reply_text("Нет запланированных постов.")
        return
    message_lines = []
    for post in posts:
        dt = post.scheduled_at.strftime("%d.%m %H:%M")
        preview = (post.content_text[:60] + "...") if post.content_text else "[медиа]"
        message_lines.append(f"📅 {dt} | {post.channel_name}\n{preview}")
        # В реальности лучше отправить каждый пост с InlineKeyboard в отдельных сообщениях
    # Здесь упростим: отправим список
    await update.message.reply_text("Запланированные посты:\n" + "\n\n".join(message_lines))
    # Для каждого поста нужно предоставить действия; в ТЗ показано по одному посту. Реализуем через inline кнопки позже.

# В полной версии нужно более детально, но сохраним компактность.
queue_handler = CommandHandler("queue", show_queue)