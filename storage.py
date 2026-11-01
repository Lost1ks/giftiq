import aiosqlite
import time
from config import DB_PATH


async def init_db():
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
        try:
            await db.execute("ALTER TABLE users ADD COLUMN art_credits INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()


async def user_upsert(user_id, username, full_name, referred_by=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, username, full_name, referred_by, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name",
            (user_id, username, full_name, referred_by, int(time.time()))
        )
        await db.commit()


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


async def gift_update_price(slug, price_ton, market):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO prices (slug, price_ton, market, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET price_ton=?, market=?, updated_at=?",
            (slug, price_ton, market, int(time.time()),
             price_ton, market, int(time.time()))
        )
        await db.execute(
            "UPDATE gifts SET last_price_ton=?, last_market=? WHERE slug=?",
            (price_ton, market, slug)
        )
        await db.commit()


async def payment_record(user_id, stars, payload):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO payments (user_id, stars, payload, paid_at) VALUES (?, ?, ?, ?)",
            (user_id, stars, payload, int(time.time()))
        )
        await db.commit()


async def premium_grant(user_id, days):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT premium_until FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        current = row[0] if row else 0
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
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(art_credits,0) FROM users WHERE user_id=?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row or row[0] <= 0:
            return False
        await db.execute(
            "UPDATE users SET art_credits = art_credits - 1 WHERE user_id=?", (user_id,)
        )
        await db.commit()
        return True


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
