import httpx
import logging
import re
from config import TONNEL_URL, MRKT_URL, PORTALS_URL

log = logging.getLogger('markets')

async def tonnel_floor(slug: str):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f'{TONNEL_URL}/api/pageGifts',
                json={'filter': json.dumps({'gift_name': slug, 'status':'listed'}),
                      'limit': 1, 'sort': {'price': 1}}
            )
            data = r.json()
            if data and len(data) > 0:
                return float(data[0].get('price', 0)), 'tonnel'
    except Exception as e:
        log.warning(f'tonnel_floor {slug}: {e}')
    return None, None

async def mrkt_floor(slug: str):
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(
                f'{MRKT_URL}/api/items',
                params={'search': slug, 'sort': 'price_asc', 'limit': 1}
            )
            data = r.json()
            items = data.get('items') or data.get('listings') or []
            if items:
                return float(items[0].get('price', 0)), 'mrkt'
    except Exception as e:
        log.warning(f'mrkt_floor {slug}: {e}')
    return None, None

async def get_floor(slug: str):
    import asyncio
    results = await asyncio.gather(tonnel_floor(slug), mrkt_floor(slug))
    valid = [(p, m) for p, m in results if p and p > 0]
    if not valid: return None, None
    return min(valid, key=lambda x: x[0])

async def parse_gift_url(url: str):
    m = re.match(r'https?://t\.me/nft/([A-Za-z0-9]+)-(\d+)', url)
    if not m: return None
    slug_name = m.group(1)
    number = int(m.group(2))
    name = re.sub(r'([A-Z])', r' \1', slug_name).strip()
    return {'slug': f'{slug_name}-{number}', 'name': name, 'number': number}

import json