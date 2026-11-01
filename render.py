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

    d.ellipse([-250, -250, 550, 550], fill=accent + (80,))
    d.ellipse([W - 500, H - 500, W + 250, H + 250], fill=accent + (70,))
    d.ellipse([W - 300, 150, W - 50, 400], fill=(255, 255, 255, 40))
    d.ellipse([100, H - 400, 400, H - 100], fill=(255, 255, 255, 30))

    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=100))
    img = img.convert('RGBA')
    img = Image.alpha_composite(img, overlay)
    return img.convert('RGB')


def _shadow(d, xy, text, font, fill):
    x, y = xy
    for dx, dy in [(3, 3), (5, 5)]:
        d.text((x + dx, y + dy), text, fill=(0, 0, 0), font=font)
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
    img = _add_decor(img, accent)
    d = ImageDraw.Draw(img)

    f_logo = _font(160, bold=True)
    f_sub = _font(60, bold=False)
    f_big = _font(130, bold=True)
    f_mid = _font(56, bold=False)
    f_small = _font(44, bold=True)

    _shadow(d, (60, 100), 'GiftIQ', f_logo, (255, 255, 255))
    _shadow(d, (60, 290), f'Collection @{user_name}', f_sub, (220, 220, 240))

    _shadow(d, (60, 440), f'{total_ton:.2f} TON', f_big, accent)
    rub = f'{int(total_rub):,}'.replace(',', ' ')
    _shadow(d, (60, 590), f'~ {rub} rub', f_mid, (220, 220, 240))

    _shadow(d, (60, 760), 'Top gifts:', f_sub, (255, 255, 255))
    y = 880
    for i, g in enumerate(gifts[:5], 1):
        d.ellipse([60, y + 10, 110, y + 60], fill=accent, outline=(255, 255, 255), width=2)
        _shadow(d, (140, y), f'{i}. {g["name"]} #{g["number"]}',
                f_small, (255, 255, 255))
        _shadow(d, (140, y + 55),
                f'   {(g["last_price_ton"] or 0):.2f} TON',
                f_small, accent)
        y += 150

    _shadow(d, (60, H - 160), 'Free case inside', f_small, (255, 220, 120))
    _shadow(d, (60, H - 90), 't.me/giftiq_tg_bot', f_mid, (200, 210, 230))

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
        _shadow(d, xy, text, font, color)
    return img


def collection_gif(user_name: str, gifts: list, total_ton: float, total_rub: float, rub_per_ton: float):
    W, H = 1080, 1920
    frames = []
    f_logo = _font(180, bold=True)
    f_sub = _font(72, bold=False)
    f_big = _font(150, bold=True)
    f_mid = _font(72, bold=False)
    f_small = _font(56, bold=True)
    f_num = _font(100, bold=True)

    c1, c2, accent = PALETTES[0]
    rub = f'{int(total_rub):,}'.replace(',', ' ')
    intro = _frame(c1, c2, accent, [
        ((60, 400), 'GiftIQ', f_logo, (255, 255, 255)),
        ((60, 640), f'@{user_name}', f_sub, (220, 220, 240)),
        ((60, 820), 'Collection', f_sub, (220, 220, 240)),
        ((60, 980), f'{total_ton:.2f} TON', f_big, accent),
        ((60, 1180), f'~ {rub} rub', f_mid, (220, 220, 240)),
        ((60, H - 100), 't.me/giftiq_tg_bot', f_small, (200, 210, 230)),
    ])
    frames.append(intro)
    frames.append(intro.copy())

    for i, g in enumerate(gifts[:10]):
        c1, c2, accent = PALETTES[i % len(PALETTES)]
        price = g['last_price_ton'] or 0
        rub_g = f'{int(price * rub_per_ton):,}'.replace(',', ' ')
        name = (g['name'] or 'Gift')[:14]
        number = g['number'] or 0
        frame = _frame(c1, c2, accent, [
            ((60, 180), f'TOP {i + 1}', f_num, (220, 220, 240)),
            ((60, 420), name, f_big, (255, 255, 255)),
            ((60, 640), f'No. {number}', f_sub, (220, 220, 240)),
            ((60, 880), f'{price:.2f} TON', f_big, accent),
            ((60, 1080), f'~ {rub_g} rub', f_mid, (220, 220, 240)),
            ((60, H - 100), 't.me/giftiq_tg_bot', f_small, (200, 210, 230)),
        ])
        frames.append(frame)

    c1, c2, accent = PALETTES[0]
    outro = _frame(c1, c2, accent, [
        ((60, 400), 'Your tracker', f_sub, (255, 255, 255)),
        ((60, 580), 'GiftIQ', f_logo, accent),
        ((60, 900), 't.me/giftiq_tg_bot', f_big, (255, 255, 255)),
        ((60, 1180), 'Free NFT case inside', f_mid, (255, 220, 120)),
    ])
    frames.append(outro)
    frames.append(outro.copy())

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        duration=1500,
        loop=0,
        optimize=True
    )
    buf.seek(0)
    return buf
