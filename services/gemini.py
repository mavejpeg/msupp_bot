import logging
import google.generativeai as genai
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = (
    "Улучши текст для Telegram-поста: сделай его живым, лаконичным, с характером. "
    "Сохрани смысл и тон автора. Верни только улучшенный текст, без пояснений."
)

async def improve_text(text: str) -> str:
    try:
        response = await model.generate_content_async(
            f"{SYSTEM_PROMPT}\n\n{text}"
        )
        improved = response.text.strip()
        if improved and improved != text:
            return improved
        else:
            logger.warning("Gemini вернул пустой или тот же текст")
            return text
    except Exception as e:
        logger.error(f"Gemini error: {e}", exc_info=True)
        return text  # fallback
