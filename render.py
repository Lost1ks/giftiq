from PIL import Image, ImageDraw, ImageFont
import io

def collection_card(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), (18, 22, 46))
    d = ImageDraw.Draw(img)
    try:
        f_big = ImageFont.truetype('arial.ttf', 72)
        f_mid = ImageFont.truetype('arial.ttf', 48)
        f_small = ImageFont.truetype('arial.ttf', 36)
    except:
        f_big = ImageFont.load_default()
        f_mid = ImageFont.load_default()
        f_small = ImageFont.load_default()
    d.text((60, 80), '💎 GiftIQ', fill=(255, 255, 255), font=f_big)
    d.text((60, 180), f'Коллекция @{user_name}', fill=(180, 190, 230), font=f_mid)
    d.text((60, 280), f'{total_ton:.2f} TON', fill=(100, 200, 255), font=f_big)
    d.text((60, 380), f'≈ {total_rub:,.0f} ₽'.replace(',', ' '),
           fill=(180, 190, 230), font=f_mid)
    d.text((60, 500), 'Топ подарков:', fill=(255, 255, 255), font=f_mid)
    y = 580
    for i, g in enumerate(gifts[:5], 1):
        d.text((60, y), f'{i}. {g["name"]} #{g["number"]}',
               fill=(255, 255, 255), font=f_small)
        d.text((60, y + 50), f'   {g["last_price_ton"]:.2f} TON',
               fill=(100, 200, 255), font=f_small)
        y += 140
    d.text((60, H - 120), 't.me/giftiq_tg_bot',
           fill=(140, 160, 200), font=f_small)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return buf