import asyncio
import json
import logging
import re
import time

import httpx

from config import RUB_PER_TON

log = logging.getLogger('markets')

PORTALS_API = 'https://portal-market.com/api'
TONNEL_API = 'https://gifts2.tonnel.network/api/pageGifts'
TONAPI_RATES = 'https://tonapi.io/v2/rates?tokens=ton&currencies=rub'

PORTALS_TTL = 600     # floor-цены всех коллекций обновляем раз в 10 минут
RATE_TTL = 3600       # курс TON → ₽ раз в час

CHROME_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/121.0.0.0 Safari/537.36'),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Origin': 'https://tonnel.network',
    'Referer': 'https://tonnel.network/',
}

_portals_cache = {'at': 0.0, 'data': {}}
_rate_cache = {'at': 0.0, 'rub': RUB_PER_TON}
_portals_lock = asyncio.Lock()


def collection_key(slug: str) -> str:
    """SnoopDogg-471247 / Snoop Dogg / Durov’s Cap -> snoopdogg / durovscap"""
    return re.sub(r'[^a-z0-9]', '', re.sub(r'-\d+$', '', slug).lower())


def _slug_to_name(slug: str) -> str:
    return re.sub(r'([A-Z])', r' \1', slug).strip()


async def portals_collections():
    """{key: {'name': 'Durov’s Cap', 'floor': 421.0}} по всем коллекциям Portals."""
    async with _portals_lock:
        if time.time() - _portals_cache['at'] < PORTALS_TTL and _portals_cache['data']:
            return _portals_cache['data']
        data = {}
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                offset = 0
                while offset < 2000:
                    r = await c.get(f'{PORTALS_API}/collections',
                                    params={'limit': 100, 'offset': offset},
                                    headers={'User-Agent': CHROME_HEADERS['User-Agent']})
                    r.raise_for_status()
                    cols = r.json().get('collections') or []
                    for col in cols:
                        key = col.get('short_name') or collection_key(col.get('name', ''))
                        try:
                            floor = float(col.get('floor_price') or 0)
                        except ValueError:
                            floor = 0.0
                        data[key] = {'name': col.get('name') or key, 'floor': floor}
                    if len(cols) < 100:
                        break
                    offset += 100
        except Exception as e:
            log.warning(f'portals collections: {e}')
        if data:
            _portals_cache.update(at=time.time(), data=data)
            log.info(f'portals: {len(data)} коллекций')
        return _portals_cache['data']


async def portals_floor(key: str):
    col = (await portals_collections()).get(key)
    if col and col['floor'] > 0:
        return round(col['floor'], 2)
    return None


async def tonnel_floor(name: str):
    flt = {
        'price': {'$exists': True},
        'refund': {'$ne': True},
        'buyer': {'$exists': False},
        'export_at': {'$exists': True},
        'gift_name': name.replace('’', "'"),
        'asset': 'TON',
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.post(TONNEL_API, json={
                'page': 1, 'limit': 1,
                'sort': '{"price":1,"gift_id":-1}',
                'filter': json.dumps(flt),
                'price_range': None, 'user_auth': '',
            }, headers=CHROME_HEADERS)
        items = r.json() if r.status_code == 200 and 'json' in r.headers.get('content-type', '') else None
        log.info(f'tonnel "{name}": status={r.status_code} items={len(items) if isinstance(items, list) else "-"}')
        if isinstance(items, list) and items:
            price = float(items[0].get('price') or 0)
            if price > 0:
                return round(price, 2)
    except Exception as e:
        log.warning(f'tonnel "{name}": {e}')
    return None


async def get_quotes(slug: str):
    """Цены коллекции на всех доступных маркетах.
    -> {'key', 'name', 'prices': {'portals': 5.57, 'tonnel': 5.2}}"""
    key = collection_key(slug)
    cols = await portals_collections()
    name = cols.get(key, {}).get('name') or _slug_to_name(slug.split('-')[0])
    p_portals, p_tonnel = await asyncio.gather(portals_floor(key), tonnel_floor(name))
    prices = {m: p for m, p in (('portals', p_portals), ('tonnel', p_tonnel)) if p}
    return {'key': key, 'name': name, 'prices': prices}


async def get_floor(slug: str):
    """Минимальная цена среди маркетов: (price, market) или (None, None)."""
    q = await get_quotes(slug)
    if not q['prices']:
        log.info(f'floor unknown {slug}')
        return None, None
    market = min(q['prices'], key=q['prices'].get)
    return q['prices'][market], market


async def ton_rub() -> float:
    if time.time() - _rate_cache['at'] < RATE_TTL:
        return _rate_cache['rub']
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(TONAPI_RATES)
            rub = float(r.json()['rates']['TON']['prices']['RUB'])
            if rub > 0:
                _rate_cache.update(at=time.time(), rub=rub)
    except Exception as e:
        log.warning(f'курс TON: {e}')
        _rate_cache['at'] = time.time() - RATE_TTL + 300  # повторим через 5 минут
    return _rate_cache['rub']


async def top_collections(n=5):
    cols = await portals_collections()
    return sorted(((c['name'], c['floor']) for c in cols.values() if c['floor'] > 0),
                  key=lambda x: -x[1])[:n]


def parse_gift_url(url: str):
    m = re.search(r't\.me/nft/([A-Za-z0-9]+)-(\d+)', url)
    if not m:
        return None
    slug_name = m.group(1)
    number = int(m.group(2))
    return {'slug': f'{slug_name}-{number}', 'name': _slug_to_name(slug_name), 'number': number}
