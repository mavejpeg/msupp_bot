import google.generativeai as genai
from config import GEMINI_API_KEY

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
        return response.text.strip()
    except Exception as e:
        print(f"Gemini error: {e}")
        return text  # fallback