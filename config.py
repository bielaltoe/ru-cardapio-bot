from dotenv import load_dotenv
import os


class Config:
    def __init__(self):
        load_dotenv()

        self.APP_ENV = os.getenv("APP_ENV")
        is_dev = self.APP_ENV == "dev"

        # Telegram
        self.TELEGRAM_TOKEN = (
            os.getenv("TELEGRAM_DEV_TOKEN") if is_dev else None
        ) or os.getenv("TELEGRAM_TOKEN")
        self.CHANNEL_ID = (
            os.getenv("CHANNEL_DEV_ID") if is_dev else None
        ) or os.getenv("CHANNEL_ID")

        # Gemini
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

        # WhatsApp (Evolution API compatible gateway)
        self.WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL")
        self.WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY")
        self.WHATSAPP_INSTANCE = os.getenv("WHATSAPP_INSTANCE")
        self.WHATSAPP_GROUP_ID = (
            os.getenv("WHATSAPP_DEV_GROUP_ID") if is_dev else None
        ) or os.getenv("WHATSAPP_GROUP_ID")
