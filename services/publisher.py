import re
import logging
from datetime import datetime
from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode
from telegram.error import TelegramError
from config import BOT_TOKEN, OWNER_ID, CHANNEL_1_ID, CHANNEL_2_ID, CHANNEL_3_ID, CHANNEL_1_LINK, CHANNEL_2_LINK, CHANNEL_3_LINK
from database import async_session, ScheduledPost

logger = logging.getLogger(__name__)
bot = Bot(token=BOT_TOKEN)

def escape_markdown(text: str) -> str:
    """Экранирует символы, которые могут сломать Markdown-разметку."""
    # Экранируем только те символы, которые действительно мешают
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

CHANNELS = {
    1: {
        "id": CHANNEL_1_ID,
        "name": "Лайфстайл",
        "link": CHANNEL_1_LINK,
        "sign": f"[Артём хз | Подписаться]({CHANNEL_1_LINK})"
    },
    2: {
        "id": CHANNEL_2_ID,
        "name": "Веб-дизайн",
        "link": CHANNEL_2_LINK,
        "sign": f"[Arto.ism | Подписаться]({CHANNEL_2_LINK})"
    },
    3: {
        "id": CHANNEL_3_ID,
        "name": "Новости",
        "link": CHANNEL_3_LINK,
        "sign": f"[ЧЁ | Подписаться]({CHANNEL_3_LINK})"
    },
}

async def notify_owner(text: str):
    """Отправляет владельцу сообщение с поддержкой Markdown.
    Вызывающий код должен экранировать переменные в тексте самостоятельно."""
    try:
        await bot.send_message(chat_id=OWNER_ID, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Failed to notify owner: {e}")
        # Попробуем отправить без форматирования
        try:
            await bot.send_message(chat_id=OWNER_ID, text=text)
        except Exception as e2:
            logger.error(f"Failed completely to notify owner: {e2}")

async def publish_now(post_data: dict, creator_id: int):
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
        safe_name = escape_markdown(ch["name"])
        await notify_owner(f"✅ Пост опубликован в *{safe_name}* в {now}")
    except TelegramError as e:
        safe_name = escape_markdown(ch["name"])
        await notify_owner(f"❌ Ошибка публикации в *{safe_name}*: {escape_markdown(str(e))}")
        raise

async def publish_scheduled(post_id: int):
    async with async_session() as session:
        post = await session.get(ScheduledPost, post_id)
        if not post or post.status != "pending":
            return
        ch = CHANNELS[post.channel_id]
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
            safe_name = escape_markdown(ch["name"])
            await notify_owner(f"✅ Запланированный пост опубликован в *{safe_name}* в {now}")
        except TelegramError as e:
            safe_name = escape_markdown(ch["name"])
            await notify_owner(f"❌ Ошибка публикации запланированного поста (id {post.id}) в *{safe_name}*: {escape_markdown(str(e))}")

def _build_caption(text: str, signature: str) -> str:
    if text:
        return f"{text}\n\n{signature}"
    return signature
