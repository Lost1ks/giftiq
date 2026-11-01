from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os

FONT_BOLD_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
FONT_REG_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def _font(size, bold=True):
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    if os.path.exists(path):
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _gradient_bg(w, h, c1, c2):
    img = Image.new('RGB', (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        r = y / (h - 1)
        rr = int(c1[0] * (1 - r) + c2[0] * r)
        gg = int(c1[1] * (1 - r) + c2[1] * r)
        bb = int(c1[2] * (1 - r) + c2[2] * r)
        d.line([(0, y), (w, y)], fill=(rr, gg, bb))
    return img


def _add_decor(img, accent):
    W, H = img.size
    overlay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    d.ellipse([-200, -200, 500, 500], fill=accent + (60,))
    d.ellipse([W - 400, H - 400, W + 200, H + 200], fill=accent + (50,))
    d.ellipse([W - 300, 100, W - 50, 350], fill=(255, 255, 255, 30))

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=80))
    img = img.convert('RGBA')
    img = Image.alpha_composite(img, overlay)
    return img.convert('RGB')


def _text_shadow(d, xy, text, font, fill, shadow=(0, 0, 0, 180)):
    x, y = xy
    for dx, dy in [(2, 2), (3, 3), (4, 4)]:
        d.text((x + dx, y + dy), text, fill=shadow[:3], font=font)
    d.text(xy, text, fill=fill, font=font)


PALETTES = [
    ((35, 15, 70),  (90, 40, 180),   (180, 120, 255)),
    ((15, 25, 60),  (40, 90, 180),   (120, 200, 255)),
    ((50, 15, 50),  (150, 50, 120),  (255, 150, 200)),
    ((10, 40, 40),  (30, 120, 110),  (120, 255, 200)),
    ((60, 25, 10),  (180, 90, 30),   (255, 200, 100)),
]


def collection_card(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    c1, c2, accent = PALETTES[0]
    img = _gradient_bg(W, H, c1, c2)
    img = _add_decor(img, accent[:3])
    d = ImageDraw.Draw(img)

    f_title = _font(140, bold=True)
    f_sub = _font(64, bold=False)
    f_big = _font(130, bold=True)
    f_mid = _font(58, bold=False)
    f_small = _font(44, bold=True)

    _text_shadow(d, (60, 90), '💎 GiftIQ', f_title, (255, 255, 255))
    _text_shadow(d, (60, 260), f'Коллекция @{user_name}', f_sub, (220, 220, 240))

    _text_shadow(d, (60, 420), f'{total_ton:.2f} TON', f_big, accent)
    rub = f'{int(total_rub):,}'.replace(',', ' ')
    _text_shadow(d, (60, 580), f'~ {rub} ₽', f_mid, (220, 220, 240))

    _text_shadow(d, (60, 760), 'Топ подарков:', f_sub, (255, 255, 255))
    y = 900
    for i, g in enumerate(gifts[:5], 1):
        d.ellipse([60, y + 10, 110, y + 60], fill=accent)
        _text_shadow(d, (140, y), f'{i}. {g["name"]} #{g["number"]}',
                     f_small, (255, 255, 255))
        _text_shadow(d, (140, y + 55),
                     f'   {(g["last_price_ton"] or 0):.2f} TON',
                     f_small, accent)
        y += 150

    _text_shadow(d, (60, H - 140), '🎁 Бесплатный кейс внутри',
                 f_small, (255, 220, 120))
    _text_shadow(d, (60, H - 80), 't.me/giftiq_tg_bot',
                 f_mid, (200, 210, 230))

    buf = io.BytesIO()
    img.save(buf, 'PNG')
    buf.seek(0)
    return buf


def _frame(bg1, bg2, accent, texts):
    W, H = 1080, 1920
    img = _gradient_bg(W, H, bg1, bg2)
    img = _add_decor(img, accent)
    d = ImageDraw.Draw(img)
    for xy, text, font, color in texts:
        _text_shadow(d, xy, text, font, color)
    return img


def collection_gif(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    frames = []
    f_title = _font(150, bold=True)
    f_sub = _font(72, bold=False)
    f_big = _font(170, bold=True)
    f_mid = _font(80, bold=False)
    f_small = _font(56, bold=True)

    c1, c2, accent = PALETTES[0]
    rub = f'{int(total_rub):,}'.replace(',', ' ')
    intro = _frame(c1, c2, accent, [
        ((60, 500), '💎 GiftIQ', f_title, (255, 255, 255)),
        ((60, 700), f'@{user_name}', f_sub, (220, 220, 240)),
        ((60, 920), f'{total_ton:.2f} TON', f_big, accent),
        ((60, 1140), f'~ {rub} ₽', f_mid, (220, 220, 240)),
        ((60, H - 100), 't.me/giftiq_tg_bot', f_small, (200, 210, 230)),
    ])
    frames.append(intro)
    frames.append(intro.copy())

    for i, g in enumerate(gifts[:10]):
        c1, c2, accent = PALETTES[i % len(PALETTES)]
        price = g['last_price_ton'] or 0
        rub_g = f'{int(price * 350):,}'.replace(',', ' ')
        frame = _frame(c1, c2, accent, [
            ((60, 180), f'#{i + 1}', f_title, (255, 255, 255) + (0,)[:0] or (255, 255, 255)),
            ((60, 420), g['name'][:16], f_big, (255, 255, 255)),
            ((60, 660), f'№ {g["number"]}', f_sub, (220, 220, 240)),
            ((60, 940), f'{price:.2f} TON', f_big, accent),
            ((60, 1180), f'~ {rub_g} ₽', f_mid, (220, 220, 240)),
            ((60, H - 100), 't.me/giftiq_tg_bot', f_small, (200, 210, 230)),
        ])
        frames.append(frame)

    c1, c2, accent = PALETTES[0]
    outro = _frame(c1, c2, accent, [
        ((60, 500), 'Твой трекер:', f_sub, (255, 255, 255)),
        ((60, 680), '@giftiq_tg_bot', f_big, accent),
        ((60, 920), '🎁 Беспл. кейс', f_sub, (255, 220, 120)),
        ((60, 1060), 'внутри бота', f_sub, (255, 220, 120)),
    ])
    frames.append(outro)
    frames.append(outro.copy())

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=1300,
        loop=0,
        optimize=True
    )
    buf.seek(0)
    return buf
