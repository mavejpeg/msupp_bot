from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, filters
from database import get_user, add_user, async_session, User
from config import OWNER_ID

async def addeditor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("Только владелец может управлять редакторами.")
        return
    if not context.args or len(context.args) != 1 or not context.args[0].startswith("@"):
        await update.message.reply_text("Использование: /addeditor @username")
        return
    username = context.args[0][1:]
    # здесь нужно получить telegram_id по username — можно через API? Не обязательно, можно хранить username.
    # Упростим: в таблице users поле username, telegram_id можно получить из сообщений, но мы не знаем id.
    # По условию редактор добавляется по @username. Для упрощения будем требовать, чтобы пользователь уже написал боту хоть раз,
    # чтобы сохранить его telegram_id. При первом взаимодействии можно сохранять в БД. Здесь предположим, что пользователь уже есть.
    async with async_session() as session:
        # Ищем по username
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            await update.message.reply_text("Пользователь с таким username не найден в базе бота. Попросите его отправить любое сообщение боту.")
            return
        user.role = "editor"
        await session.commit()
    await update.message.reply_text(f"✅ @{username} теперь редактор.")

async def removeeditor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # аналогично
    ...

handlers = [
    CommandHandler("addeditor", addeditor, filters=filters.User(OWNER_ID)),
    CommandHandler("removeeditor", removeeditor, filters=filters.User(OWNER_ID)),
]