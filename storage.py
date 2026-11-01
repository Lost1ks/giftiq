import os
import time

import aiosqlite

from config import DB_PATH


async def init_db():
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            referred_by INTEGER,
            premium_until INTEGER DEFAULT 0,
            notify_pct INTEGER DEFAULT 10,
            art_credits INTEGER DEFAULT 0,
            created_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            slug TEXT,
            name TEXT,
            number INTEGER,
            last_price_ton REAL,
            last_market TEXT,
            added_at INTEGER,
            UNIQUE(user_id, slug)
        );
        CREATE TABLE IF NOT EXISTS prices (
            slug TEXT PRIMARY KEY,
            price_ton REAL,
            market TEXT,
            updated_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            stars INTEGER,
            payload TEXT,
            paid_at INTEGER
        );
        """)
        for ddl in ("ALTER TABLE users ADD COLUMN art_credits INTEGER DEFAULT 0",
                    "ALTER TABLE payments ADD COLUMN charge_id TEXT"):
            try:
                await db.execute(ddl)
            except Exception:
                pass
        await db.commit()


async def user_upsert(user_id, username, full_name, referred_by=None):
    """Возвращает True, если пользователь новый."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)) as cur:
            exists = await cur.fetchone() is not None
        await db.execute(
            "INSERT INTO users (user_id, username, full_name, referred_by, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name",
            (user_id, username, full_name, referred_by, int(time.time()))
        )
        await db.commit()
        return not exists


async def user_exists(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone() is not None


async def gift_add(user_id, slug, name, number, price_ton, market):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO gifts (user_id, slug, name, number, last_price_ton, last_market, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, slug, name, number, price_ton, market, int(time.time()))
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def gift_remove(user_id, slug):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("DELETE FROM gifts WHERE user_id=? AND slug=?", (user_id, slug))
        await db.commit()
        return cur.rowcount > 0


async def gifts_list(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT slug, name, number, last_price_ton, last_market FROM gifts "
            "WHERE user_id=? ORDER BY last_price_ton DESC",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [
                {'slug': r[0], 'name': r[1], 'number': r[2],
                 'last_price_ton': r[3], 'last_market': r[4]}
                for r in rows
            ]


async def all_gift_slugs():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT slug FROM gifts") as cur:
            return [r[0] for r in await cur.fetchall()]


async def price_get(slug):
    """(price_ton, market) последней сохранённой цены или (0, None)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT price_ton, market FROM prices WHERE slug=?", (slug,)) as cur:
            row = await cur.fetchone()
    return (row[0] or 0, row[1]) if row else (0, None)


async def gift_update_price(slug, price_ton, market, name=None):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO prices (slug, price_ton, market, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET price_ton=excluded.price_ton, "
            "market=excluded.market, updated_at=excluded.updated_at",
            (slug, price_ton, market, now)
        )
        await db.execute(
            "UPDATE gifts SET last_price_ton=?, last_market=?, name=COALESCE(?, name) WHERE slug=?",
            (price_ton, market, name, slug)
        )
        await db.commit()


async def premium_users_with_slug(slug):
    """[(user_id, notify_pct)] премиум-пользователей, у которых есть этот подарок."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT u.user_id, COALESCE(u.notify_pct, 10) FROM gifts g "
            "JOIN users u ON u.user_id = g.user_id "
            "WHERE g.slug=? AND u.premium_until > ?",
            (slug, int(time.time()))
        ) as cur:
            return await cur.fetchall()


async def payment_record(user_id, stars, payload, charge_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, stars, payload, paid_at, charge_id) VALUES (?, ?, ?, ?, ?)",
            (user_id, stars, payload, int(time.time()), charge_id)
        )
        await db.commit()


async def premium_get(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
    return (row[0] or 0) if row else 0


async def premium_grant(user_id, days):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT premium_until FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        current = (row[0] or 0) if row else 0
        base = max(current, int(time.time()))
        new_until = base + days * 86400
        await db.execute(
            "UPDATE users SET premium_until=? WHERE user_id=?",
            (new_until, user_id)
        )
        await db.commit()
        return new_until


async def art_grant(user_id, count=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET art_credits = COALESCE(art_credits,0) + ? WHERE user_id=?",
            (count, user_id)
        )
        await db.commit()


async def art_get(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(art_credits,0) FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0


async def art_use(user_id):
    """Атомарно списывает 1 генерацию. False — если генераций нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE users SET art_credits = art_credits - 1 "
            "WHERE user_id=? AND COALESCE(art_credits,0) > 0", (user_id,)
        )
        await db.commit()
        return cur.rowcount > 0


async def stats_get():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            u = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE premium_until > ?",
            (int(time.time()),)
        ) as cur:
            p = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT SUM(stars) FROM payments WHERE paid_at > ?",
            (int(time.time()) - 86400,)
        ) as cur:
            s = (await cur.fetchone())[0] or 0
        async with db.execute("SELECT COUNT(*) FROM gifts") as cur:
            g = (await cur.fetchone())[0]
    return {'users': u, 'premium': p, 'stars_24h': s, 'gifts': g}
