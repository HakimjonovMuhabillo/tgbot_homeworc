import os

from dotenv import load_dotenv


load_dotenv('.env')


DATABASE_URL = os.getenv("DATABASE_URL", default='postgres://postgres:123rasulQq@localhost:5432/tg')


TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7550488248:AAGlTub1djRHzFgPqVrt-J78_65d5aBh1ng')

API_URL = os.getenv('API_URL')