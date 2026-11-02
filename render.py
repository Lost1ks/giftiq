import io
import math
import os
import random
import shutil
import subprocess
import tempfile
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
CRYSTAL_PATH = os.path.join(HERE, 'assets', 'crystal.png')

FONT_BOLD = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'C:/Windows/Fonts/arialbd.ttf']
FONT_REG = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'C:/Windows/Fonts/arial.ttf']

BASE_W, BASE_H = 720, 1280   # макет в «базовых» пикселях, масштабируется под размер кадра
FPS = 20
WHITE = (255, 255, 255)
SOFT = (210, 212, 240)
GOLD = (255, 210, 120)

# фон сверху, фон снизу, акцент, второй акцент
PALETTES = [
    ((8, 4, 28), (46, 14, 100), (178, 120, 255), (70, 140, 255)),
    ((4, 10, 30), (16, 48, 116), (100, 190, 255), (150, 90, 255)),
    ((20, 4, 26), (92, 20, 92), (255, 130, 215), (140, 90, 255)),
    ((2, 18, 24), (10, 72, 84), (100, 240, 210), (80, 140, 255)),
    ((22, 10, 4), (92, 46, 12), (255, 196, 96), (255, 110, 150)),
]


@lru_cache(maxsize=64)
def _font(size, bold=True):
    for path in (FONT_BOLD if bold else FONT_REG):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _glyph(f, size, ch):
    im = Image.new('L', (size * 2, size * 2), 0)
    ImageDraw.Draw(im).text((0, 0), ch, font=f, fill=255)
    return im.tobytes()


@lru_cache(maxsize=8)
def _rub(size):
    """'₽', если в шрифте есть такой символ, иначе 'руб'."""
    f = _font(size, False)
    has = _glyph(f, size, '₽') != _glyph(f, size, '\uE000')
    return '₽' if has else 'руб'


def _fmt_rub(rub, size):
    return f'≈ {int(rub):,} {_rub(size)}'.replace(',', ' ')


@lru_cache(maxsize=64)
def _glow(size, color, alpha):
    """Мягкое круглое свечение size×size."""
    r = Image.radial_gradient('L').resize((size, size))
    a = r.point(lambda v: int(max(0, 255 - v) ** 2 / 255 * alpha / 255))
    g = Image.new('RGBA', (size, size), color + (0,))
    g.putalpha(a)
    return g


@lru_cache(maxsize=64)
def _sparkle(size):
    """Четырёхлучевая звёздочка ✦ со свечением."""
    s = max(size, 4)
    c = s / 2
    w = s * 0.09
    m = Image.new('L', (s, s), 0)
    d = ImageDraw.Draw(m)
    d.polygon([(c, 0), (c + w, c - w), (s, c), (c + w, c + w),
               (c, s), (c - w, c + w), (0, c), (c - w, c - w)], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(max(0.6, s / 40)))
    glow = Image.radial_gradient('L').resize((s, s)).point(lambda v: int(max(0, 255 - v * 1.6) * 0.45))
    m = ImageChops.lighter(m, glow)
    sp = Image.new('RGBA', (s, s), WHITE + (0,))
    sp.putalpha(m)
    return sp


@lru_cache(maxsize=16)
def _crystal(width):
    im = Image.open(CRYSTAL_PATH).convert('RGBA')
    return im.resize((width, int(width * im.height / im.width)), Image.LANCZOS)


@lru_cache(maxsize=16)
def _background(W, H, pal_idx):
    """Статичный космический фон: градиент, туманности, звёзды, виньетка."""
    top, bottom, acc, acc2 = PALETTES[pal_idx]
    s = W / BASE_W
    grad = Image.linear_gradient('L').resize((W, H))
    img = Image.composite(Image.new('RGB', (W, H), bottom), Image.new('RGB', (W, H), top), grad).convert('RGBA')
    rnd = random.Random(pal_idx * 7 + W)
    for _ in range(5):   # туманности
        size = int(rnd.uniform(380, 760) * s)
        col = acc if rnd.random() < 0.5 else acc2
        img.alpha_composite(_glow(size, col, rnd.randint(40, 80)),
                            (int(rnd.uniform(-0.2, 0.9) * W), int(rnd.uniform(-0.1, 0.95) * H)))
    stars = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(stars)
    for _ in range(int(260 * s)):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        r = rnd.choice([0.6, 0.8, 1.0, 1.0, 1.4, 1.9]) * s
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(70, 230)))
    img.alpha_composite(stars)
    vign = Image.radial_gradient('L').resize((W, H)).point(lambda v: int(min(255, max(0, v - 150) * 1.6)))
    dark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dark.putalpha(vign)
    img.alpha_composite(dark)
    return img


def _sparkles_layer(img, pal_idx, t, s):
    """Мерцающие звёздочки: размер и яркость меняются по синусу."""
    W, H = img.size
    rnd = random.Random(1000 + pal_idx)
    for _ in range(16):
        x, y = rnd.uniform(0.04, 0.96) * W, rnd.uniform(0.03, 0.97) * H
        base = rnd.uniform(14, 34) * s
        k = (math.sin(2 * math.pi * (t / rnd.uniform(1.6, 2.8)) + rnd.uniform(0, 6.3)) + 1) / 2
        size = int(base * (0.35 + 0.65 * k))
        if size < 4:
            continue
        sp = _sparkle(size)
        if k < 0.98:
            sp = sp.copy()
            sp.putalpha(sp.getchannel('A').point(lambda v: int(v * (0.25 + 0.75 * k))))
        img.alpha_composite(sp, (int(x - size / 2), int(y - size / 2)))


def _moving_glows(img, pal_idx, t, s):
    W, H = img.size
    _, _, acc, acc2 = PALETTES[pal_idx]
    for i, (col, cx, cy, rad) in enumerate([(acc, 0.25, 0.22, 0.10), (acc2, 0.78, 0.78, 0.12)]):
        size = int(620 * s)
        a = 2 * math.pi * (t / 6 + i * 0.5)
        x = int((cx + rad * math.cos(a)) * W - size / 2)
        y = int((cy + rad * 0.6 * math.sin(a)) * H - size / 2)
        img.alpha_composite(_glow(size, col, 70), (x, y))


def _place_crystal(img, cx, cy, width, t, pal_idx):
    acc = PALETTES[pal_idx][2]
    pulse = 0.75 + 0.25 * math.sin(2 * math.pi * t / 2.2)
    g = int(width * 1.5)
    img.alpha_composite(_glow(g, acc, int(110 * pulse)), (int(cx - g / 2), int(cy - g / 2)))
    cr = _crystal(width)
    dy = int(math.sin(2 * math.pi * t / 3) * width * 0.03)
    img.alpha_composite(cr, (int(cx - cr.width / 2), int(cy - cr.height / 2 + dy)))


class _Layer:
    """Слой с текстом и стеклянными панелями (рисуется один раз на слайд)."""

    def __init__(self, W, H):
        self.s = W / BASE_W
        self.img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        self.shadow = Image.new('L', (W, H), 0)
        self.panels = []

    def p(self, v):
        return int(v * self.s)

    def panel(self, x0, y0, x1, y1, radius=34):
        box = [self.p(x0), self.p(y0), self.p(x1), self.p(y1)]
        d = ImageDraw.Draw(self.img)
        d.rounded_rectangle(box, self.p(radius), fill=(255, 255, 255, 24),
                            outline=(255, 255, 255, 70), width=max(1, self.p(2)))
        d.line([box[0] + self.p(radius), box[1] + self.p(1), box[2] - self.p(radius), box[1] + self.p(1)],
               fill=(255, 255, 255, 120), width=max(1, self.p(2)))
        self.panels.append((box, self.p(radius)))

    def pill(self, cx, cy, text, size, fill, color=(20, 10, 40)):
        f = _font(self.p(size), True)
        w = f.getlength(text)
        pad_x, pad_y = self.p(26), self.p(12)
        box = [self.p(cx) - w / 2 - pad_x, self.p(cy) - pad_y,
               self.p(cx) + w / 2 + pad_x, self.p(cy) + self.p(size) * 1.15 + pad_y]
        ImageDraw.Draw(self.img).rounded_rectangle(box, (box[3] - box[1]) / 2, fill=fill + (255,))
        ImageDraw.Draw(self.img).text((self.p(cx), self.p(cy)), text, font=f, fill=color, anchor='mt')

    def text(self, x, y, text, size, color=WHITE, bold=True, anchor='mt', max_w=640):
        size = self.p(size)
        f = _font(size, bold)
        while f.getlength(text) > self.p(max_w) and size > 12:
            size = int(size * 0.92)
            f = _font(size, bold)
        xy = (self.p(x), self.p(y))
        ImageDraw.Draw(self.shadow).text((xy[0], xy[1] + self.p(3)), text, font=f, fill=200, anchor=anchor)
        ImageDraw.Draw(self.img).text(xy, text, font=f, fill=color, anchor=anchor)

    def done(self):
        sh = self.shadow.filter(ImageFilter.GaussianBlur(self.p(6)))
        out = Image.new('RGBA', self.img.size, (0, 0, 0, 0))
        out.putalpha(sh.point(lambda v: int(v * 0.7)))
        out.alpha_composite(self.img)
        self.img = out
        return self


def _shine(img, panels, progress, s):
    """Блик, пробегающий по стеклянным панелям (progress 0..1)."""
    if not 0 < progress < 1:
        return
    for (x0, y0, x1, y1), radius in panels:
        w, h = x1 - x0, y1 - y0
        band_w = int(120 * s)
        band = Image.linear_gradient('L').rotate(90, expand=True).resize((band_w, h))
        band = ImageChops.multiply(band, band.transpose(Image.FLIP_LEFT_RIGHT)).point(lambda v: int(v * 0.32))
        layer = Image.new('L', (w, h), 0)
        layer.paste(band, (int(-band_w + (w + band_w) * progress), 0))
        layer = layer.transform((w, h), Image.AFFINE, (1, 0.35, -h * 0.17, 0, 1, 0))
        mask = Image.new('L', (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius, fill=255)
        layer = ImageChops.multiply(layer, mask)
        white = Image.new('RGBA', (w, h), WHITE + (0,))
        white.putalpha(layer)
        img.alpha_composite(white, (x0, y0))


# ---------- слайды анимации ----------

def _slide_intro(L, user_name, total_ton, total_rub, acc):
    L.text(360, 430, 'GiftIQ', 96)
    L.text(360, 548, f'@{user_name}', 34, SOFT, bold=False)
    L.panel(60, 620, 660, 900)
    L.text(360, 650, 'Стоимость коллекции', 30, SOFT, bold=False)
    L.text(360, 705, f'{total_ton:.2f} TON', 84, acc)
    L.text(360, 820, _fmt_rub(total_rub, L.p(38)), 38, SOFT, bold=False)
    L.text(360, 1205, 't.me/giftiq_tg_bot', 30, (200, 205, 235))


def _slide_gift(L, i, n, g, rate, acc):
    price = g['last_price_ton'] or 0
    L.pill(360, 150, f'TOP {i + 1}', 34, acc)
    L.text(360, 520, g['name'] or 'Gift', 70, max_w=640)
    L.text(360, 615, f'#{g["number"] or 0}', 36, SOFT, bold=False)
    L.panel(60, 700, 660, 980)
    L.text(360, 728, 'Floor-цена', 30, SOFT, bold=False)
    L.text(360, 782, f'{price:.2f} TON', 88, acc)
    L.text(360, 900, _fmt_rub(price * rate, L.p(38)), 38, SOFT, bold=False)
    d = ImageDraw.Draw(L.img)
    for k in range(n):
        x = L.p(360 + (k - (n - 1) / 2) * 30)
        r = L.p(7 if k == i else 5)
        d.ellipse([x - r, L.p(1110) - r, x + r, L.p(1110) + r],
                  fill=(acc + (255,)) if k == i else (255, 255, 255, 90))
    L.text(360, 1205, 't.me/giftiq_tg_bot', 30, (200, 205, 235))


def _slide_outro(L, acc):
    L.text(360, 590, 'Твой трекер TG-подарков', 36, SOFT, bold=False)
    L.text(360, 645, 'GiftIQ', 104, acc)
    L.panel(70, 820, 650, 1010)
    L.text(360, 850, 't.me/giftiq_tg_bot', 44)
    L.text(360, 935, 'Бесплатный кейс внутри', 32, GOLD)


def _ease(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def _frames(user_name, gifts, total_ton, total_rub, rate, W, H):
    """Генератор кадров RGB всей анимации."""
    s = W / BASE_W
    top = gifts[:5]
    slides = [('intro', 0, 2.6)] + [('gift', i, 2.2) for i in range(len(top))] + [('outro', 0, 2.8)]
    layers = []
    for idx, (kind, i, dur) in enumerate(slides):
        pal = 0 if kind != 'gift' else (i + 1) % len(PALETTES)
        acc = PALETTES[pal][2]
        L = _Layer(W, H)
        if kind == 'intro':
            _slide_intro(L, user_name, total_ton, total_rub, acc)
        elif kind == 'gift':
            _slide_gift(L, i, len(top), top[i], rate, acc)
        else:
            _slide_outro(L, acc)
        layers.append((kind, pal, dur, L.done()))

    def bg_frame(pal, kind, t):
        img = _background(W, H, pal).copy()
        _moving_glows(img, pal, t, s)
        _sparkles_layer(img, pal, t, s)
        if kind == 'intro':
            _place_crystal(img, W / 2, 255 * s, int(330 * s), t, pal)
        elif kind == 'outro':
            _place_crystal(img, W / 2, 360 * s, int(400 * s), t, pal)
        elif kind == 'gift':
            _place_crystal(img, W / 2, 330 * s, int(210 * s), t, pal)
        return img

    fade = 0.35
    for idx, (kind, pal, dur, L) in enumerate(layers):
        n = int(dur * FPS)
        for f in range(n):
            t = f / FPS
            img = bg_frame(pal, kind, t)
            k = _ease(t / 0.5)
            txt = L.img
            if k < 1:
                txt = L.img.copy()
                txt.putalpha(txt.getchannel('A').point(lambda v: int(v * k)))
            img.alpha_composite(txt, (0, int((1 - k) * 40 * s)))
            _shine(img, L.panels, (t - 0.7) / 0.9, s)
            if idx + 1 < len(layers) and t > dur - fade:
                nk, npal, _, _ = layers[idx + 1]
                img = Image.blend(img, bg_frame(npal, nk, 0), (t - (dur - fade)) / fade)
            yield img.convert('RGB')


def collection_gif(user_name: str, gifts: list, total_ton: float, total_rub: float, rub_per_ton: float):
    """Анимация для сторис. MP4 (если есть ffmpeg) или GIF. -> (BytesIO, filename)"""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        W, H = 720, 1280
        fd, path = tempfile.mkstemp(suffix='.mp4')
        os.close(fd)
        try:
            proc = subprocess.Popen(
                [ffmpeg, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                 '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264',
                 '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
                 '-movflags', '+faststart', path],
                stdin=subprocess.PIPE)
            for fr in _frames(user_name, gifts, total_ton, total_rub, rub_per_ton, W, H):
                proc.stdin.write(fr.tobytes())
            proc.stdin.close()
            if proc.wait(timeout=120) == 0:
                with open(path, 'rb') as fh:
                    return io.BytesIO(fh.read()), 'giftiq.mp4'
        finally:
            os.remove(path)
    # запасной вариант без ffmpeg: GIF, 12 кадров/с, 540×960
    W, H = 540, 960
    frames = [fr.quantize(colors=200, dither=Image.Dither.NONE)
              for k, fr in enumerate(_frames(user_name, gifts, total_ton, total_rub, rub_per_ton, W, H))
              if k % 2 == 0]
    buf = io.BytesIO()
    frames[0].save(buf, format='GIF', save_all=True, append_images=frames[1:],
                   duration=int(2000 / FPS), loop=0, optimize=False)
    buf.seek(0)
    return buf, 'giftiq.gif'


# ---------- карточка (PNG) ----------

def collection_card(user_name: str, gifts: list, total_ton: float, total_rub: float):
    W, H = 1080, 1920
    s = W / BASE_W
    pal = 0
    acc = PALETTES[pal][2]
    img = _background(W, H, pal).copy()
    _moving_glows(img, pal, 0.4, s)
    _sparkles_layer(img, pal, 0.4, s)
    _place_crystal(img, W / 2, 190 * s, int(270 * s), 0.0, pal)

    L = _Layer(W, H)
    L.text(360, 330, 'GiftIQ', 80)
    L.text(360, 425, f'@{user_name}', 30, SOFT, bold=False)
    L.panel(50, 490, 670, 750)
    L.text(360, 515, 'Стоимость коллекции', 28, SOFT, bold=False)
    L.text(360, 565, f'{total_ton:.2f} TON', 76, acc)
    L.text(360, 670, _fmt_rub(total_rub, L.p(34)), 34, SOFT, bold=False)
    top = gifts[:5]
    L.text(60, 795, 'Топ подарков', 34, anchor='lt')
    L.panel(50, 850, 670, 850 + len(top) * 70 + 30)
    d = ImageDraw.Draw(L.img)
    for i, g in enumerate(top):
        y = 880 + i * 70
        d.ellipse([L.p(80), L.p(y - 2), L.p(124), L.p(y + 42)], fill=acc + (255,))
        L.text(102, y + 6, str(i + 1), 26, (20, 10, 40))
        L.text(145, y + 4, f'{g["name"]} #{g["number"]}', 28, anchor='lt', max_w=330)
        L.text(640, y + 4, f'{(g["last_price_ton"] or 0):.2f} TON', 28, acc, anchor='rt', max_w=170)
    L.text(360, 1160, 'Бесплатный кейс внутри', 28, GOLD)
    L.text(360, 1205, 't.me/giftiq_tg_bot', 32, (200, 205, 235))
    img.alpha_composite(L.done().img)

    buf = io.BytesIO()
    img.convert('RGB').save(buf, 'PNG', optimize=True)
    buf.seek(0)
    return buf
