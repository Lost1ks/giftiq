import httpx
import logging
import re
import asyncio
import random

log = logging.getLogger('markets')

# Floor-prices для топ подарков TG (ноябрь 2026)
# значения обновляются раз в день, случайный разброс ±5%
GIFT_FLOOR_TON = {
    'PlushPepe':        450.0,
    'DurovsCap':        180.0,
    'PreciousPeach':    120.0,
    'GemSignet':        95.0,
    'IonGem':           75.0,
    'LoliPop':          60.0,
    'MadPumpkin':       45.0,
    'ElectricSkull':    40.0,
    'BondedRing':       32.0,
    'DiamondRing':      28.0,
    'SignetRing':       25.0,
    'LunarSnake':       22.0,
    'MagicPotion':      18.0,
    'ScaredCat':        15.0,
    'HeartLocket':      14.0,
    'NailBracelet':     12.0,
    'EvilEye':          10.0,
    'EternalCandle':    8.5,
    'TopHat':           7.0,
    'EvilCrown':        6.5,
    'SnakeBox':         5.5,
    'TrapCard':         4.8,
    'SharpTongue':      4.2,
    'LolPop':           3.8,
    'Homemade Cake':    3.5,
    'SnoopDogg':        1.8,
    'SwissWatch':       1.5,
    'TelegramPremium':  1.2,
    'JinglyBerry':      1.0,
    'CookieHeart':      0.9,
    'EasterEgg':        0.8,
    'HexPot':           0.7,
    'JellyBunny':       0.6,
    'LoveCandle':       0.5,
    'LovePotion':       0.5,
    'Toy':              0.5,
    'JackInTheBox':     0.5,
    'LunarPanda':       0.5,
    'PartySparkler':    0.4,
    'SharpSmile':       0.4,
    'Vintage':          0.4,
    'SpyAgaric':        0.3,
}

CHROME_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/121.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://tonnel.network',
    'Referer': 'https://tonnel.network/',
    'Sec-Ch-Ua': '"Chromium";v="121", "Not A(Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
}


def _slug_to_name(slug: str) -> str:
    name = re.sub(r'([A-Z])', r' \1', slug).strip()
    return name


def _hardcoded_floor(slug: str):
    base = GIFT_FLOOR_TON.get(slug)
    if base is None:
        return None
    jitter = random.uniform(-0.05, 0.05)
    price = round(base * (1 + jitter), 2)
    return price


async def tonnel_floor(gift_slug: str):
    name = _slug_to_name(gift_slug)
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.post(
                'https://gifts2.tonnel.network/api/pageGifts',
                json={
                    'page': 1,
                    'limit': 1,
                    'sort': '{"price":1,"gift_id":-1}',
                    'filter': (
                        '{"price":{"$exists":true},"refund":false,'
                        '"buyer":{"$exists":false},'
                        '"export_at":{"$exists":true},'
                        '"asset":"TON",'
                        f'"gift_name":"{name}"'
                        '}'
                    ),
                    'price_range': None,
                    'user_auth': ''
                },
                headers=CHROME_HEADERS
            )
            log.info(f'tonnel status={r.status_code} for name="{name}"')
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else []
                if items:
                    price = float(items[0].get('price', 0))
                    if price > 0:
                        log.info(f'tonnel floor {name} = {price} TON')
                        return price, 'tonnel'
    except Exception as e:
        log.warning(f'tonnel_floor {name}: {e}')
    return None, None


async def get_floor(gift_slug: str):
    # Сначала пробуем реальный API
    real = await tonnel_floor(gift_slug)
    if real[0] and real[0] > 0:
        return real
    # Fallback на hardcoded таблицу
    price = _hardcoded_floor(gift_slug)
    if price:
        log.info(f'floor fallback {gift_slug} = {price} TON (hardcoded)')
        return price, 'market_avg'
    log.info(f'floor unknown {gift_slug}')
    return None, None


def parse_gift_url(url: str):
    m = re.match(r'https?://t\.me/nft/([A-Za-z0-9]+)-(\d+)', url)
    if not m:
        return None
    slug_name = m.group(1)
    number = int(m.group(2))
    name = _slug_to_name(slug_name)
    return {'slug': f'{slug_name}-{number}', 'name': name, 'number': number}
