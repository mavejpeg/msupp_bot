import logging
import google.generativeai as genai
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)

# Автоматический выбор лучшей бесплатной модели
_fallback_model = "models/gemini-1.5-flash"
model = None

try:
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
    
    # Приоритет: flash-latest → pro-latest → любая flash-модель → стандартная
    preferred = [m for m in available_models if 'flash-latest' in m]
    if not preferred:
        preferred = [m for m in available_models if 'pro-latest' in m]
    if not preferred:
        preferred = [m for m in available_models if 'flash' in m.lower()]
    
    if preferred:
        model_name = preferred[0]
    else:
        model_name = _fallback_model
    
    model = genai.GenerativeModel(model_name)
    logger.info(f"Используется модель Gemini: {model_name}")

except Exception as e:
    logger.warning(f"Не удалось получить список моделей: {e}. Использую {_fallback_model}.")
    model = genai.GenerativeModel(_fallback_model)

# Системный промт для улучшения текста
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
            logger.warning("Gemini вернул пустой или идентичный текст")
            return text
    except Exception as e:
        logger.error(f"Gemini error: {e}", exc_info=True)
        return text
