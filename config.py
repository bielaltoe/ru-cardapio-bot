from dotenv import load_dotenv
import os

class Config:
    def __init__(self):
        load_dotenv()

        # Informações do Telegram

        self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        self.CHANNEL_ID = os.getenv("CHANNEL_ID")
        self.GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

        # Alterna para DEV caso APP_ENV=dev
        self.APP_ENV = os.getenv("APP_ENV")
        if self.APP_ENV == "dev":
            self.TELEGRAM_TOKEN = os.getenv("TELEGRAM_DEV_TOKEN", self.TELEGRAM_TOKEN)
            self.CHANNEL_ID = os.getenv("CHANNEL_DEV_ID", self.CHANNEL_ID)

   