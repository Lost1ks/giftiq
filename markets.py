import httpx
import logging
import re
import asyncio

log = logging.getLogger('markets')

TONNEL_API = 'https://gifts2.tonnel.network/api/pageGifts'
MRKT_API = 'https://mrkt.app/api/items'


def _slug_to_name(slug: str) -> str:
    name = re.sub(r'([A-Z])', r' \1', slug).strip()
    return name


async def tonnel_floor(gift_slug: str):
    name = _slug_to_name(gift_slug)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                TONNEL_API,
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
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 GiftIQ/1.0'
                }
            )
            log.info(f'tonnel status={r.status_code} for name="{name}"')
            if r.status_code != 200:
                log.warning(f'tonnel non-200: {r.text[:200]}')
                return None, None

            data = r.json()
            log.info(f'tonnel data type={type(data).__name__} '
                     f'len={len(data) if hasattr(data, "__len__") else "?"} '
                     f'preview={str(data)[:200]}')

            items = data if isinstance(data, list) else (data.get('gifts') or data.get('items') or [])
            if not items:
                log.info(f'tonnel: нет листингов для {name}')
                return None, None

            first = items[0]
            price = first.get('price') or first.get('priceTON') or 0
            try:
                price = float(price)
            except Exception:
                price = 0.0
            if price > 0:
                log.info(f'tonnel floor {name} = {price} TON')
                return price, 'tonnel'
            return None, None
    except Exception as e:
        log.exception(f'tonnel_floor {name}: {e}')
    return None, None


async def mrkt_floor(gift_slug: str):
    name = _slug_to_name(gift_slug)
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                MRKT_API,
                params={
                    'search': name,
                    'sort': 'price_asc',
                    'limit': 1
                },
                headers={'User-Agent': 'Mozilla/5.0 GiftIQ/1.0'}
            )
            log.info(f'mrkt status={r.status_code} for name="{name}"')
            if r.status_code != 200:
                return None, None

            data = r.json()
            items = data.get('items') or data.get('listings') or data.get('data') or []
            if not items:
                return None, None

            first = items[0]
            price = first.get('price') or first.get('price_ton') or 0
            try:
                price = float(price)
            except Exception:
                price = 0.0
            if price > 0:
                log.info(f'mrkt floor {name} = {price} TON')
                return price, 'mrkt'
            return None, None
    except Exception as e:
        log.exception(f'mrkt_floor {name}: {e}')
    return None, None


async def get_floor(gift_slug: str):
    results = await asyncio.gather(
        tonnel_floor(gift_slug),
        mrkt_floor(gift_slug),
        return_exceptions=True
    )
    valid = []
    for res in results:
        if isinstance(res, tuple) and res[0] and res[0] > 0:
            valid.append(res)
    if not valid:
        return None, None
    return min(valid, key=lambda x: x[0])


def parse_gift_url(url: str):
    m = re.match(r'https?://t\.me/nft/([A-Za-z0-9]+)-(\d+)', url)
    if not m:
        return None
    slug_name = m.group(1)
    number = int(m.group(2))
    name = _slug_to_name(slug_name)
    return {'slug': f'{slug_name}-{number}', 'name': name, 'number': number}
