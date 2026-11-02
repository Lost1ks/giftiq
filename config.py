import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ['BOT_TOKEN']
ADMIN_USER_ID = int(os.environ.get('ADMIN_USER_ID', '0'))
OPENROUTER_KEY = os.environ.get('OPENROUTER_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
# gemini-2.5-flash-image-preview удалена Google (404), рабочая модель — без -preview
GEMINI_IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')
# запасной генератор картинок: Cloudflare Workers AI (FLUX), бесплатный лимит
CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID', '')
CF_API_TOKEN = os.environ.get('CF_API_TOKEN', '')
TON_ADDRESS = os.environ.get('TON_ADDRESS', '')
TONNEL_REF = os.environ.get('TONNEL_REF', '')
EPIC_GIFT_REF = os.environ.get('EPIC_GIFT_REF', '')
XROCKET_REF = os.environ.get('XROCKET_REF', '')
CHANNEL_URL = os.environ.get('CHANNEL_URL', 'https://t.me/giftIQ_news')
WEBAPP_URL = os.environ.get('WEBAPP_URL', 'https://lost1ks.github.io/giftiq-landing/app/?v=3')  # ?v= сбрасывает кэш Telegram после правок приложения
REVEAL_PRICE = int(os.environ.get('REVEAL_PRICE', '500'))
PREMIUM_PRICE = int(os.environ.get('PREMIUM_PRICE', '500'))
ART_PRICE = int(os.environ.get('ART_PRICE', '100'))
REF_BONUS_DAYS = int(os.environ.get('REF_BONUS_DAYS', '7'))
DB_PATH = os.environ.get('DB_PATH', '/app/data/giftiq.db')

TONNEL_URL = 'https://tonnel.network'
MRKT_URL = 'https://mrkt.app'
# запасной курс, если tonapi.io недоступен; обычно курс берётся живой (markets.ton_rub)
RUB_PER_TON = float(os.environ.get('RUB_PER_TON', '100'))
