import logging
from datetime import datetime
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config import BOT_TOKEN, OWNER_ID, CHANNEL_1_ID, CHANNEL_2_ID, CHANNEL_3_ID, CHANNEL_1_LINK, CHANNEL_2_LINK, CHANNEL_3_LINK
from database import async_session, ScheduledPost
from sqlalchemy import update

logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN)

CHANNELS = {
    1: {"id": CHANNEL_1_ID, "name": "Лайфстайл", "link": CHANNEL_1_LINK, "sign": "[Артём хз](t.me/CHANNEL_1_LINK) | Подписаться"},
    2: {"id": CHANNEL_2_ID, "name": "Веб-дизайн", "link": CHANNEL_2_LINK, "sign": "[Arto.ism](t.me/CHANNEL_2_LINK) | Подписаться"},
    3: {"id": CHANNEL_3_ID, "name": "Новости", "link": CHANNEL_3_LINK, "sign": "[ЧЁ](t.me/CHANNEL_3_LINK) | Подписаться"},
}

async def notify_owner(text: str):
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Failed to notify owner: {e}")

async def publish_now(post_data: dict, creator_id: int):
    """Немедленная публикация поста"""
    ch_num = post_data["channel"]
    ch = CHANNELS[ch_num]
    caption = _build_caption(post_data.get("text", ""), ch["sign"])
    media = post_data.get("media")
    media_type = post_data.get("media_type", "text")
    try:
        if media_type == "text":
            await bot.send_message(chat_id=ch["id"], text=caption, parse_mode=ParseMode.MARKDOWN)
        elif media_type == "photo":
            await bot.send_photo(chat_id=ch["id"], photo=media[0], caption=caption, parse_mode=ParseMode.MARKDOWN)
        elif media_type == "album":
            media_group = [InputMediaPhoto(media=file_id) for file_id in media]
            media_group[0].caption = caption
            media_group[0].parse_mode = ParseMode.MARKDOWN
            await bot.send_media_group(chat_id=ch["id"], media=media_group)
        now = datetime.now().strftime("%H:%M %d.%m")
        await notify_owner(f"✅ Пост опубликован в *{ch['name']}* в {now}")
    except TelegramError as e:
        await notify_owner(f"❌ Ошибка публикации в *{ch['name']}*: {str(e)}")
        raise

async def publish_scheduled(post_id: int):
    """Вызывается планировщиком"""
    async with async_session() as session:
        post = await session.get(ScheduledPost, post_id)
        if not post or post.status != "pending":
            return
        ch_num = post.channel_id
        # для этого нужно маппирование channel_id на номер; сохраним удобнее
        # будем хранить channel_code (1/2/3) в БД
        ch = CHANNELS[post.channel_id]  # если channel_id это код 1/2/3
        caption = _build_caption(post.content_text or "", ch["sign"])
        media_ids = post.media_file_ids or []
        media_type = post.media_type
        try:
            if media_type == "text":
                await bot.send_message(chat_id=ch["id"], text=caption, parse_mode=ParseMode.MARKDOWN)
            elif media_type == "photo":
                await bot.send_photo(chat_id=ch["id"], photo=media_ids[0], caption=caption, parse_mode=ParseMode.MARKDOWN)
            elif media_type == "album":
                media_group = [InputMediaPhoto(media=file_id) for file_id in media_ids]
                media_group[0].caption = caption
                media_group[0].parse_mode = ParseMode.MARKDOWN
                await bot.send_media_group(chat_id=ch["id"], media=media_group)
            post.status = "sent"
            await session.commit()
            now = datetime.now().strftime("%H:%M %d.%m")
            await notify_owner(f"✅ Запланированный пост опубликован в *{ch['name']}* в {now}")
        except TelegramError as e:
            await notify_owner(f"❌ Ошибка публикации запланированного поста (id {post.id}) в *{ch['name']}*: {str(e)}")

def _build_caption(text: str, signature: str) -> str:
    if text:
        return f"{text}\n\n{signature}"
    return signature