import asyncio, logging, time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import aiosqlite
from config import DB_PATH, RUB_PER_TON
import markets
import storage

log = logging.getLogger('jobs')

async def refresh_all_prices(bot):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT slug FROM gifts") as cur:
            rows = await cur.fetchall()
    log.info(f'refresh_prices: {len(rows)} уникальных подарков')
    for (slug,) in rows:
        name = slug.split('-')[0]
        price, market = await markets.get_floor(name)
        if price:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT price_ton FROM prices WHERE slug=?", (slug,)
                ) as cur:
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
        async with db.execute(
            "SELECT user_id FROM gifts WHERE slug=?", (slug,)
        ) as cur:
            uids = [r[0] for r in await cur.fetchall()]
        for uid in uids:
            async with db.execute(
                "SELECT premium_until FROM users WHERE user_id=?", (uid,)
            ) as cur:
                row = await cur.fetchone()
            if not row or row[0] < time.time():
                continue
            try:
                await bot.send_message(uid,
                    f'{arrow} <b>{slug}</b>: {pct:+.1f}%\n'
                    f'было {old:.2f} TON → стало {new:.2f} TON',
                    parse_mode='HTML'
                )
            except Exception as e:
                log.warning(f'notify {uid}: {e}')

def setup_scheduler(bot):
    s = AsyncIOScheduler()
    s.add_job(refresh_all_prices, IntervalTrigger(minutes=30),
              args=[bot], max_instances=1)
    return s