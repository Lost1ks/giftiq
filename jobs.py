import asyncio
import datetime
import logging
import os
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from config import EPIC_GIFT_REF
import markets
import storage

log = logging.getLogger('jobs')

CHANNEL = os.environ.get('CHANNEL_USERNAME', '')
BOT_LINK = 'https://t.me/giftiq_tg_bot'
MARKET_NAMES = {'portals': 'Portals', 'tonnel': 'Tonnel'}
# старые цены с этими метками были выдуманы (таблица + случайный разброс) — по ним не алертим
UNTRUSTED_MARKETS = {None, 'unknown', 'market_avg'}


def epic_link():
    base = 'https://t.me/epic_gift_bot/app'
    if EPIC_GIFT_REF:
        return f'{base}?startapp=ref_{EPIC_GIFT_REF}'
    return base


def rub_str(ton: float, rate: float) -> str:
    return f'{int(ton * rate):,}'.replace(',', ' ')


async def _post_top(bot):
    top = await markets.top_collections(5)
    if not top:
        return None
    rate = await markets.ton_rub()
    lines = ['<b>💎 ТОП-5 дорогих подарков TG сегодня (floor):</b>\n']
    for i, (name, price) in enumerate(top, 1):
        lines.append(f'<b>{i}. {name}</b> — {price:.1f} TON (~{rub_str(price, rate)} ₽)')
    lines.append(f'\n📊 Твой трекер: {BOT_LINK}')
    return '\n'.join(lines)


async def _post_gift_of_day(bot):
    top = await markets.top_collections(30)
    if not top:
        return None
    name, price = random.choice(top)
    rate = await markets.ton_rub()
    return (
        f'🔥 <b>Подарок дня: {name}</b>\n\n'
        f'Floor: <b>{price:.1f} TON</b> (~{rub_str(price, rate)} ₽)\n\n'
        f'Хочешь оценить свою коллекцию?\n'
        f'→ {BOT_LINK}'
    )


async def _post_epic_case(bot):
    return (
        '🎁 <b>Напоминание</b>\n\n'
        'Бесплатный кейс в Epic Gift обновляется каждые 24 часа.\n'
        'Можно забрать новый NFT подарок.\n\n'
        f'Открыть кейс: {epic_link()}\n'
        f'Трекер коллекции: {BOT_LINK}'
    )


async def _post_rarity(bot):
    return (
        '✨ <b>А ты знал?</b>\n\n'
        'У каждого подарка TG есть атрибуты (Model, Backdrop, Symbol) '
        'с разной редкостью.\n\n'
        'Редкая комбинация может стоить в разы дороже floor-цены коллекции.\n\n'
        f'Узнай, сколько стоит твоя коллекция: {BOT_LINK}'
    )


async def _post_cta(bot):
    return (
        '📊 <b>Коллекционируешь TG подарки?</b>\n\n'
        'Бесплатный трекер:\n'
        '• Общая стоимость коллекции в TON и ₽\n'
        '• Floor-цены с Portals и Tonnel\n'
        '• Карточка и анимация для сторис\n'
        '• Бесплатный NFT-кейс внутри\n\n'
        f'👉 {BOT_LINK}'
    )


POST_GENERATORS = [
    _post_top,
    _post_gift_of_day,
    _post_epic_case,
    _post_rarity,
    _post_cta,
]


async def post_to_channel(bot):
    if not CHANNEL:
        log.warning('CHANNEL_USERNAME не задан, пропускаю пост')
        return
    gen = random.choice(POST_GENERATORS)
    try:
        text = await gen(bot)
        if not text:
            log.info(f'{gen.__name__}: пустой текст, пропускаю')
            return
        await bot.send_message(CHANNEL, text, parse_mode='HTML', disable_web_page_preview=True)
        log.info(f'пост в {CHANNEL} отправлен ({gen.__name__})')
    except Exception as e:
        log.exception(f'post_to_channel: {e}')


async def refresh_prices(bot, slugs=None):
    """Обновляет цены подарков. Премиум-юзерам шлёт пуш при изменении floor на ±notify_pct%."""
    slugs = slugs if slugs is not None else await storage.all_gift_slugs()
    log.info(f'refresh: {len(slugs)} подарков')
    floors = {}   # key коллекции -> (price, market, name), чтобы не дёргать маркеты по каждому экземпляру
    alerts = {}   # (user_id, key) -> текст, чтобы на одну коллекцию был один пуш
    for slug in slugs:
        key = markets.collection_key(slug)
        if key not in floors:
            q = await markets.get_quotes(slug)
            if q['prices']:
                m = min(q['prices'], key=q['prices'].get)
                floors[key] = (q['prices'][m], m, q['name'])
            else:
                floors[key] = (None, None, q['name'])
            await asyncio.sleep(0.5)
        price, market, name = floors[key]
        if not price:
            continue
        old_price, old_market = await storage.price_get(slug)
        await storage.gift_update_price(slug, price, market, name)
        if bot is None or old_price <= 0 or old_market in UNTRUSTED_MARKETS:
            continue
        pct = (price - old_price) / old_price * 100
        for uid, notify_pct in await storage.premium_users_with_slug(slug):
            if abs(pct) >= (notify_pct or 10):
                arrow = '📈' if pct > 0 else '📉'
                alerts[(uid, key)] = (
                    f'{arrow} <b>{name}</b>: {pct:+.1f}%\n'
                    f'floor было {old_price:.2f} TON → стало {price:.2f} TON '
                    f'({MARKET_NAMES.get(market, market)})'
                )
    for (uid, _), text in alerts.items():
        try:
            await bot.send_message(uid, text, parse_mode='HTML')
        except Exception as e:
            log.warning(f'notify {uid}: {e}')
        await asyncio.sleep(0.05)
    return len(alerts)


async def refresh_all_prices(bot):
    try:
        await refresh_prices(bot)
    except Exception as e:
        log.exception(f'refresh_all_prices: {e}')


def setup_scheduler(bot):
    s = AsyncIOScheduler(timezone='Europe/Moscow')
    # первый прогон через минуту после старта — заменит старые выдуманные цены настоящими
    s.add_job(refresh_all_prices, IntervalTrigger(minutes=30),
              args=[bot], max_instances=1,
              next_run_time=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=1))
    s.add_job(post_to_channel, CronTrigger(hour='10,18,22', minute=5),
              args=[bot], max_instances=1)
    return s
