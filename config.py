import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

CHANNEL_1_ID = int(os.getenv("CHANNEL_1_ID", "0"))
CHANNEL_2_ID = int(os.getenv("CHANNEL_2_ID", "0"))
CHANNEL_3_ID = int(os.getenv("CHANNEL_3_ID", "0"))

CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK", "")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK", "")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK", "")

DATABASE_URL = os.getenv("DATABASE_URL")  # Railway предоставляет автоматически
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Для вебхука (Railway предоставляет PUBLIC_DOMAIN и PORT)
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # или https://{RAILWAY_PUBLIC_DOMAIN}/webhook
PORT = int(os.getenv("PORT", "8080"))