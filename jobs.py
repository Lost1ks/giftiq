import asyncio
import logging
import time
import os
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import aiosqlite

from config import DB_PATH, RUB_PER_TON, EPIC_GIFT_REF
import markets
import storage

log = logging.getLogger('jobs')

CHANNEL = os.environ.get('CHANNEL_USERNAME', '')
BOT_LINK = 'https://t.me/giftiq_tg_bot'


def epic_link():
    base = 'https://t.me/epic_gift_bot/app'
    if EPIC_GIFT_REF:
        return f'{base}?startapp=ref_{EPIC_GIFT_REF}'
    return base


TOP_GIFTS = [
    ('PlushPepe', 'Plush Pepe'),
    ('DurovsCap', "Durov's Cap"),
    ('PreciousPeach', 'Precious Peach'),
    ('GemSignet', 'Gem Signet'),
    ('IonGem', 'Ion Gem'),
    ('LoliPop', 'LoliPop'),
    ('MadPumpkin', 'Mad Pumpkin'),
    ('ElectricSkull', 'Electric Skull'),
    ('BondedRing', 'Bonded Ring'),
    ('DiamondRing', 'Diamond Ring'),
    ('ScaredCat', 'Scared Cat'),
    ('HeartLocket', 'Heart Locket'),
    ('NailBracelet', 'Nail Bracelet'),
    ('EvilEye', 'Evil Eye'),
    ('SnoopDogg', 'Snoop Dogg'),
]


def rub_str(ton: float) -> str:
    return f'{int(ton * RUB_PER_TON):,}'.replace(',', ' ')


async def _top_prices():
    results = []
    for slug, name in TOP_GIFTS[:8]:
        price, _ = await markets.get_floor(slug)
        if price and price > 0:
            results.append((name, price))
        await asyncio.sleep(0.3)
    results.sort(key=lambda x: -x[1])
    return results[:5]


async def _post_top(bot):
    top = await _top_prices()
    if not top:
        return None
    lines = ['<b>💎 ТОП-5 дорогих подарков TG сегодня:</b>\n']
    for i, (name, price) in enumerate(top, 1):
        lines.append(f'<b>{i}. {name}</b> — {price:.1f} TON (~{rub_str(price)} ₽)')
    lines.append(f'\n📊 Твой трекер: {BOT_LINK}')
    return '\n'.join(lines)


async def _post_gift_of_day(bot):
    slug, name = random.choice(TOP_GIFTS)
    price, _ = await markets.get_floor(slug)
    if not price or price <= 0:
        return None
    return (
        f'🔥 <b>Подарок дня: {name}</b>\n\n'
        f'Floor: <b>{price:.1f} TON</b> (~{rub_str(price)} ₽)\n\n'
        f'Хочешь оценить свою коллекцию?\n'
        f'→ {BOT_LINK}'
    )


async def _post_epic_case(bot):
    return (
        '🎁 <b>Напоминание</b>\n\n'
        'Бесплатный кейс в Epic Gift обновляется каждые 24 часа.\n'
        'Можно забрать новый NFT подарок — реально выводится.\n\n'
        f'Открыть кейс: {epic_link()}\n'
        f'Трекер коллекции: {BOT_LINK}'
    )


async def _post_rarity(bot):
    return (
        '✨ <b>А ты знал?</b>\n\n'
        'У каждого подарка TG есть атрибуты (Model, Backdrop, Pattern) '
        'с разной редкостью.\n\n'
        'Снайперская комбинация даёт +300-500% к рыночной цене '
        'по сравнению с базовой моделью.\n\n'
        f'Проверь редкости своей коллекции: {BOT_LINK}'
    )


async def _post_cta(bot):
    return (
        '📊 <b>Коллекционируешь TG подарки?</b>\n\n'
        'Собрал бесплатный трекер:\n'
        '• Общая стоимость коллекции в TON и ₽\n'
        '• Floor-цены по маркетам\n'
        '• Крутая анимация для сторис\n'
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


async def refresh_all_prices(bot):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT slug FROM gifts") as cur:
            rows = await cur.fetchall()
    log.info(f'refresh: {len(rows)} уникальных подарков')
    for (slug,) in rows:
        name = slug.split('-')[0]
        price, market = await markets.get_floor(name)
        if price:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT price_ton FROM prices WHERE slug=?", (slug,)) as cur:
                    old = await cur.fetchone()
            old_price = old[0] if old else 0
            await storage.gift_update_price(slug, price, market)
            if old_price > 0:
                pct = (price - old_price) / old_price * 100
                if abs(pct) >= 10:
                    await notify_users(bot, slug, old_price, price, pct)
        await asyncio.sleep(1.1)


async def notify_users(bot, slug, old, new, pct):
    arrow = '📈' if pct > 0 else '📉'
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM gifts WHERE slug=?", (slug,)) as cur:
            uids = [r[0] for r in await cur.fetchall()]
        for uid in uids:
            async with db.execute("SELECT premium_until FROM users WHERE user_id=?", (uid,)) as cur:
                row = await cur.fetchone()
            if not row or row[0] < time.time():
                continue
            try:
                await bot.send_message(
                    uid,
                    f'{arrow} <b>{slug}</b>: {pct:+.1f}%\n'
                    f'было {old:.2f} TON → стало {new:.2f} TON',
                    parse_mode='HTML'
                )
            except Exception as e:
                log.warning(f'notify {uid}: {e}')


def setup_scheduler(bot):
    s = AsyncIOScheduler(timezone='Europe/Moscow')
    s.add_job(refresh_all_prices, IntervalTrigger(minutes=30),
              args=[bot], max_instances=1)
    s.add_job(post_to_channel, CronTrigger(hour='10,18,22', minute=5),
              args=[bot], max_instances=1)
    return s
