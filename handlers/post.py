from telegram import Update, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from datetime import datetime, timedelta
import logging
from keyboards import (
    channel_selection, ai_options, ai_compare, preview_actions,
    date_selection, time_selection
)
from services.gemini import improve_text
from services.publisher import publish_now, CHANNELS, _build_caption
from database import async_session, ScheduledPost
from scheduler import add_scheduled_job
from config import OWNER_ID
from services.publisher import notify_owner

logger = logging.getLogger(__name__)

# Состояния
CHOOSE_CHANNEL, CONTENT, AI_CHOICE, PREVIEW, SCHEDULE_DATE, SCHEDULE_TIME, CUSTOM_TIME = range(7)

async def start_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберите канал:", reply_markup=channel_selection())
    return CHOOSE_CHANNEL

async def channel_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channel = int(query.data.split(":")[1])
    context.user_data["channel"] = channel
    await query.edit_message_text(f"Выбран канал: {CHANNELS[channel]['name']}\nТеперь отправьте контент (текст, фото, альбом).")
    return CONTENT

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    context.user_data["media"] = []
    context.user_data["text"] = None
    context.user_data["media_type"] = "text"

    if msg.photo:
        context.user_data["media_type"] = "photo"
        context.user_data["media"].append(msg.photo[-1].file_id)
        if msg.caption:
            context.user_data["text"] = msg.caption
    elif msg.text:
        context.user_data["text"] = msg.text
    # альбом обрабатывается через media_group, но получим позже

    if context.user_data.get("text"):
        await update.message.reply_text("Хотите улучшить текст с помощью AI?", reply_markup=ai_options())
        return AI_CHOICE
    else:
        return await show_preview(update, context)

async def media_group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка альбомов: собираем все фото из медиагруппы в context.user_data["media"]
    if not context.user_data.get("album_collected"):
        context.user_data["album_collected"] = True
        context.user_data["media"] = [msg.photo[-1].file_id for msg in update.message.photo]
        # caption берём из первого сообщения
        first_caption = update.message.caption
        if first_caption:
            context.user_data["text"] = first_caption
        context.user_data["media_type"] = "album"
        if context.user_data.get("text"):
            await update.message.reply_text("Хотите улучшить текст с помощью AI?", reply_markup=ai_options())
            return AI_CHOICE
        else:
            return await show_preview(update, context)
    else:
        # Дополнительные сообщения группы игнорируем
        return

async def ai_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ai_skip":
        return await show_preview(update, context)
    elif query.data == "ai_improve":
        original = context.user_data["text"]
        await query.edit_message_text("✨ Улучшаю текст...")
        improved = await improve_text(original)
        context.user_data["improved_text"] = improved
        await query.edit_message_text(
            f"*Оригинал:*\n{original}\n\n*Улучшенный вариант:*\n{improved}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ai_compare()
        )
        return PREVIEW  # временно, на самом деле надо обработать результат
    return await show_preview(update, context)

async def ai_result_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "take_improved":
        context.user_data["text"] = context.user_data["improved_text"]
    # иначе оставляем оригинал
    return await show_preview(update, context)

async def show_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ch = CHANNELS[context.user_data["channel"]]
    text = context.user_data.get("text", "")
    caption = _build_caption(text, ch["sign"])
    media = context.user_data.get("media", [])
    media_type = context.user_data.get("media_type", "text")

    preview_msg = None
    if media_type == "text":
        preview_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=preview_actions()
        )
    elif media_type == "photo":
        preview_msg = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=media[0],
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=preview_actions()
        )
    elif media_type == "album":
        media_group = [InputMediaPhoto(media=file_id) for file_id in media]
        media_group[0].caption = caption
        media_group[0].parse_mode = ParseMode.MARKDOWN
        preview_msg = await context.bot.send_media_group(
            chat_id=update.effective_chat.id,
            media=media_group
        )
        # для альбома клавиатура отправляется отдельным сообщением
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите действие:",
            reply_markup=preview_actions()
        )
    # удаляем предыдущее сообщение с вопросом AI, если есть
    if update.callback_query:
        await update.callback_query.message.delete()
    return PREVIEW

async def preview_actions_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data
    if action == "publish_now":
        await publish_now(context.user_data, update.effective_user.id)
        await notify_owner(f"📝 Редактор @{update.effective_user.username} создал пост в *{CHANNELS[context.user_data['channel']]['name']}*")
        await query.edit_message_text("✅ Опубликовано!")
        return ConversationHandler.END
    elif action == "schedule":
        await query.edit_message_text("Выберите дату:", reply_markup=date_selection(generate_dates()))
        return SCHEDULE_DATE
    elif action == "edit":
        # очищаем и начинаем заново
        context.user_data.clear()
        await query.edit_message_text("Давайте начнём заново. Выберите канал:", reply_markup=channel_selection())
        return CHOOSE_CHANNEL
    elif action == "cancel":
        await query.edit_message_text("Отменено.")
        return ConversationHandler.END

def generate_dates():
    today = datetime.now().date()
    return [(today + timedelta(days=i)).strftime("%d.%m") for i in range(1, 15)]

async def date_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("date:"):
        date_str = query.data.split(":")[1]
        context.user_data["scheduled_date"] = date_str
        await query.edit_message_text(f"Выбрана дата: {date_str}\nТеперь выберите время:", reply_markup=time_selection())
        return SCHEDULE_TIME
    elif query.data == "back_to_preview":
        return await show_preview(update, context)

async def time_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("time:"):
        time_str = query.data.split(":")[1]
        await schedule_post(update, context, time_str)
        return ConversationHandler.END
    elif query.data == "custom_time":
        await query.edit_message_text("Введите время в формате ЧЧ:ММ (например 09:15):")
        return CUSTOM_TIME
    elif query.data == "back_to_dates":
        await query.edit_message_text("Выберите дату:", reply_markup=date_selection(generate_dates()))
        return SCHEDULE_DATE

async def custom_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("Неверный формат. Введите ещё раз ЧЧ:ММ:")
        return CUSTOM_TIME
    await schedule_post(update, context, time_str)
    return ConversationHandler.END

async def schedule_post(update, context, time_str):
    date_str = context.user_data["scheduled_date"]
    dt_str = f"{date_str} {time_str}"
    scheduled_dt = datetime.strptime(dt_str, "%d.%m %H:%M")
    ch = CHANNELS[context.user_data["channel"]]
    media_ids = context.user_data.get("media", [])
    media_type = context.user_data.get("media_type", "text")
    text = context.user_data.get("text", "")
    creator = update.effective_user.id

    async with async_session() as session:
        post = ScheduledPost(
            channel_id=context.user_data["channel"],  # 1/2/3
            channel_name=ch["name"],
            content_text=text,
            media_file_ids=media_ids if media_ids else None,
            media_type=media_type,
            scheduled_at=scheduled_dt,
            created_by=creator,
            status="pending"
        )
        session.add(post)
        await session.commit()
        post_id = post.id

    await add_scheduled_job(post_id, scheduled_dt)
    await notify_owner(
        f"📝 Редактор @{update.effective_user.username} запланировал пост в *{ch['name']}* на {scheduled_dt.strftime('%d.%m %H:%M')}"
    )
    await update.effective_chat.send_message(
        f"📅 Запланировано в *{ch['name']}* на {scheduled_dt.strftime('%d.%m %H:%M')}",
        parse_mode=ParseMode.MARKDOWN
    )

post_conversation = ConversationHandler(
    entry_points=[CommandHandler("post", start_post)],
    states={
        CHOOSE_CHANNEL: [CallbackQueryHandler(channel_chosen, pattern=r"^ch:\d$")],
        CONTENT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_content),
            MessageHandler(filters.PHOTO, receive_content),
            MessageHandler(filters.CAPTION, receive_content),  # caption обрабатывается вместе с фото
            # Альбомы отдельно
            MessageHandler(filters.PHOTO, media_group_handler),
        ],
        AI_CHOICE: [CallbackQueryHandler(ai_choice, pattern=r"^ai_(skip|improve)$")],
        PREVIEW: [
            CallbackQueryHandler(preview_actions_handler, pattern=r"^(publish_now|schedule|edit|cancel)$"),
            CallbackQueryHandler(ai_result_choice, pattern=r"^take_(improved|original)$"),  # если был AI выбор
        ],
        SCHEDULE_DATE: [CallbackQueryHandler(date_selected, pattern=r"^(date:|back_to_preview)")],
        SCHEDULE_TIME: [CallbackQueryHandler(time_selected, pattern=r"^(time:|custom_time|back_to_dates)")],
        CUSTOM_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_time_input)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
)