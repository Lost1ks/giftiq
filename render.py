from PIL import Image, ImageDraw, ImageFont
import io


def collection_card(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H), (18, 22, 46))
    d = ImageDraw.Draw(img)

    f_big = ImageFont.load_default(size=96)
    f_mid = ImageFont.load_default(size=56)
    f_small = ImageFont.load_default(size=42)

    d.text((60, 80), 'GiftIQ', fill=(255, 255, 255), font=f_big)
    d.text((60, 200), f'Collection @{user_name}', fill=(180, 190, 230), font=f_mid)
    d.text((60, 300), f'{total_ton:.2f} TON', fill=(100, 200, 255), font=f_big)

    rub = f'{total_rub:,.0f}'.replace(',', ' ')
    d.text((60, 420), f'~ {rub} rub', fill=(180, 190, 230), font=f_mid)

    d.text((60, 560), 'Top gifts:', fill=(255, 255, 255), font=f_mid)
    y = 660
    for i, g in enumerate(gifts[:5], 1):
        d.text((60, y), f'{i}. {g["name"]} #{g["number"]}',
               fill=(255, 255, 255), font=f_small)
        d.text((60, y + 60), f'   {g["last_price_ton"]:.2f} TON',
               fill=(100, 200, 255), font=f_small)
        y += 160

    d.text((60, H - 140), 't.me/giftiq_tg_bot',
           fill=(140, 160, 200), font=f_small)

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return buf
