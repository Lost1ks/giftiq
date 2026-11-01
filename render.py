from PIL import Image, ImageDraw, ImageFont
import io


def collection_gif(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    frames = []

    palettes = [
        ((18, 22, 46),   (100, 200, 255)),
        ((45, 20, 60),   (220, 100, 255)),
        ((15, 40, 50),   (100, 255, 180)),
        ((60, 20, 20),   (255, 150, 100)),
        ((25, 25, 80),   (160, 200, 255)),
    ]

    f_big = ImageFont.load_default(size=120)
    f_mid = ImageFont.load_default(size=72)
    f_small = ImageFont.load_default(size=48)

    bg, accent = palettes[0]
    img = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(img)
    d.text((60, 400), '💎 GiftIQ', fill=(255, 255, 255), font=f_big)
    d.text((60, 580), f'@{user_name}', fill=(180, 190, 230), font=f_mid)
    d.text((60, 820), f'{total_ton:.2f} TON', fill=accent, font=f_big)
    rub = f'{int(total_rub):,}'.replace(',', ' ')
    d.text((60, 1000), f'~ {rub} rub', fill=(200, 210, 230), font=f_mid)
    d.text((60, H - 160), 't.me/giftiq_tg_bot',
           fill=(140, 160, 200), font=f_small)
    frames.append(img.copy())
    frames.append(img.copy())

    for i, g in enumerate(gifts[:10]):
        bg, accent = palettes[i % len(palettes)]
        img = Image.new('RGB', (W, H), bg)
        d = ImageDraw.Draw(img)
        d.text((60, 200), f'#{i + 1}', fill=(140, 160, 200), font=f_big)
        d.text((60, 500), g['name'], fill=(255, 255, 255), font=f_big)
        d.text((60, 700), f'№ {g["number"]}', fill=(200, 210, 230), font=f_mid)
        price = g['last_price_ton'] or 0
        d.text((60, 1000), f'{price:.2f} TON', fill=accent, font=f_big)
        if price:
            rub_g = f'{int(price * 350):,}'.replace(',', ' ')
            d.text((60, 1180), f'~ {rub_g} rub', fill=(200, 210, 230), font=f_mid)
        d.text((60, H - 160), 't.me/giftiq_tg_bot',
               fill=(140, 160, 200), font=f_small)
        frames.append(img)

    bg, accent = palettes[0]
    img = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(img)
    d.text((60, 500), 'Твой трекер:', fill=(255, 255, 255), font=f_mid)
    d.text((60, 700), '@giftiq_tg_bot', fill=accent, font=f_big)
    d.text((60, 900), 'Беспл. кейс внутри', fill=(255, 180, 100), font=f_mid)
    frames.append(img)
    frames.append(img.copy())

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=1200,
        loop=0,
        optimize=True
    )
    buf.seek(0)
    return buf
