import asyncio
import datetime
import logging
import os
import random
import re

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from aiogram.types import BufferedInputFile

from config import EPIC_GIFT_REF, ADMIN_USER_ID
import markets
import render
import storage

log = logging.getLogger('jobs')

def normalize_channel(value: str) -> str:
    """giftIQ_news / t.me/giftIQ_news / @giftIQ_news -> @giftIQ_news; числовой id оставляем как есть."""
    v = re.sub(r'^(https?://)?t\.me/', '', (value or '').strip()).strip('/')
    if v and not v.startswith('@') and not v.lstrip('-').isdigit():
        v = '@' + v
    return v


CHANNEL = normalize_channel(os.environ.get('CHANNEL_USERNAME') or '@giftIQ_news')
# автопосты 3 раза в день (топ, хиты продаж, подарок дня...). AUTO_POSTS=0 — выключить
AUTO_POSTS = os.environ.get('AUTO_POSTS', '1') != '0'
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
    lines.append(f'\n📊 Оцени свою коллекцию: {BOT_LINK}')
    photo = await asyncio.to_thread(render.top_card, 'ТОП-5 подарков', 'самые дорогие по floor-цене',
                                    [(n, f'{p:.0f} TON') for n, p in top])
    return '\n'.join(lines), photo


async def _post_hot_sales(bot):
    hot = await markets.top_sales(5)
    if not hot:
        return None
    lines = ['<b>🔥 Хиты продаж за 24 часа</b> (Portals)\n']
    for i, (name, sales, floor) in enumerate(hot, 1):
        lines.append(f'<b>{i}. {name}</b> — {sales:,} продаж, floor {floor:.1f} TON'.replace(',', ' '))
    lines.append(f'\nСледи за ценами своих подарков: {BOT_LINK}')
    photo = await asyncio.to_thread(render.top_card, 'Хиты продаж', 'больше всего сделок за 24 часа',
                                    [(n, f'{s:,} шт'.replace(',', ' ')) for n, s, _ in hot])
    return '\n'.join(lines), photo


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
    _post_hot_sales,
    _post_epic_case,
    _post_rarity,
    _post_cta,
]
_post_state = {'next': random.randrange(len(POST_GENERATORS)), 'admin_warned': False}


async def _safe(gen, bot):
    try:
        return await gen(bot)
    except Exception as e:
        log.exception(f'{gen.__name__}: {e}')
        return None


async def _notify_admin(bot, text):
    if ADMIN_USER_ID:
        try:
            await bot.send_message(ADMIN_USER_ID, text)
        except Exception:
            pass


async def publish_scheduled(bot):
    """Публикует посты из /newpost, у которых подошло время (копия сообщения админа в канал)."""
    for post_id, from_chat, msg_id in await storage.sched_due():
        try:
            await bot.copy_message(CHANNEL, from_chat, msg_id)
            await storage.sched_set_status(post_id, 'sent')
            log.info(f'запланированный пост #{post_id} опубликован')
            await _notify_admin(bot, f'Пост #{post_id} опубликован в {CHANNEL}')
        except Exception as e:
            log.exception(f'пост #{post_id}: {e}')
            await storage.sched_set_status(post_id, 'error')
            await _notify_admin(bot, f'Пост #{post_id} не опубликован: {e}\n\n'
                                     'Проверь, что бот — админ канала, и что ты не удалил сообщение с постом.')


async def post_to_channel(bot, gen=None):
    """Публикует следующий пост по кругу. -> (ok, описание)"""
    if not CHANNEL:
        log.warning('CHANNEL_USERNAME пустой, пропускаю пост')
        return False, 'канал не задан'
    if gen is None:
        # темы идут по кругу; если пост не собрался (нет данных) — берём следующий
        for _ in range(len(POST_GENERATORS)):
            gen = POST_GENERATORS[_post_state['next']]
            _post_state['next'] = (_post_state['next'] + 1) % len(POST_GENERATORS)
            post = await _safe(gen, bot)
            if post:
                break
        else:
            return False, 'нет данных ни для одного поста'
    else:
        post = await _safe(gen, bot)
        if not post:
            return False, f'{gen.__name__}: нет данных'
    text, photo = post if isinstance(post, tuple) else (post, None)
    try:
        if photo:
            await bot.send_photo(CHANNEL, BufferedInputFile(photo, filename='giftiq.png'),
                                 caption=text, parse_mode='HTML')
        else:
            await bot.send_message(CHANNEL, text, parse_mode='HTML', disable_web_page_preview=True)
        log.info(f'пост в {CHANNEL} отправлен ({gen.__name__})')
        _post_state['admin_warned'] = False
        return True, gen.__name__
    except Exception as e:
        log.exception(f'post_to_channel: {e}')
        if not _post_state['admin_warned']:
            _post_state['admin_warned'] = True
            await _notify_admin(bot, f'Не получилось опубликовать пост в {CHANNEL}: {e}\n\n'
                                     'Проверь, что бот добавлен в канал администратором '
                                     'с правом «Публикация сообщений».')
        return False, str(e)


async def auto_post(bot):
    if AUTO_POSTS:
        await post_to_channel(bot)


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
    s.add_job(auto_post, CronTrigger(hour='10,18,22', minute=5),
              args=[bot], max_instances=1)
    s.add_job(publish_scheduled, IntervalTrigger(seconds=30),
              args=[bot], max_instances=1)
    return s
