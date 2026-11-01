import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ['BOT_TOKEN']
ADMIN_USER_ID = int(os.environ.get('ADMIN_USER_ID', '0'))
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
TON_ADDRESS = os.environ.get('TON_ADDRESS', '')
TONNEL_REF = os.environ.get('TONNEL_REF', '')
EPIC_GIFT_REF = os.environ.get('EPIC_GIFT_REF', '')
XROCKET_REF = os.environ.get('XROCKET_REF', '')
REVEAL_PRICE = int(os.environ.get('REVEAL_PRICE', '500'))
PREMIUM_PRICE = int(os.environ.get('PREMIUM_PRICE', '500'))
DB_PATH = os.environ.get('DB_PATH', '/app/data/giftiq.db')

TONNEL_URL = 'https://tonnel.network'
MRKT_URL = 'https://mrkt.app'
RUB_PER_TON = 350.0
