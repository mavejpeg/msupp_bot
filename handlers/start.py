from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [["📝 Новая публикация", "📋 Очередь"]],
    resize_keyboard=True,
    is_persistent=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Главное меню",
        reply_markup=MAIN_KEYBOARD
    )
