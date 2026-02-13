import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL")
    GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD")
