import asyncio
import base64
import html
import json
import logging
import re
import time

import httpx

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery,
                           BufferedInputFile, ErrorEvent, WebAppInfo)
from aiogram.filters import Command, CommandObject

from config import (ADMIN_USER_ID, TONNEL_REF, EPIC_GIFT_REF, XROCKET_REF, CHANNEL_URL,
                    GEMINI_API_KEY, GEMINI_IMAGE_MODEL, CF_ACCOUNT_ID, CF_API_TOKEN, WEBAPP_URL,
                    PREMIUM_PRICE, ART_PRICE, REF_BONUS_DAYS)
import storage
import markets
import render
import jobs

log = logging.getLogger('handlers')
router = Router()

GIFT_LINK_RE = r't\.me/nft/[A-Za-z0-9]+-\d+'
MARKET_NAMES = {'portals': 'Portals', 'tonnel': 'Tonnel'}
REFRESH_COOLDOWN = 60
WEBAPP_MAX_GIFTS = 40
_last_refresh = {}


def tonnel_link():
    base = 'https://t.me/tonnel_network_bot'
    if TONNEL_REF:
        return f'{base}?start=ref_{TONNEL_REF}'
    return base


def epic_gift_link():
    base = 'https://t.me/epic_gift_bot/app'
    if EPIC_GIFT_REF:
        return f'{base}?startapp=ref_{EPIC_GIFT_REF}'
    return base


def xrocket_link():
    if XROCKET_REF:
        return f'https://t.me/xrocket?start=p2p_{XROCKET_REF}'
    return 'https://t.me/xrocket'


def rub_fmt(ton: float, rate: float) -> str:
    return f'{int(ton * rate):,}'.replace(',', ' ')


def market_name(m):
    return MARKET_NAMES.get(m, 'нет данных')


ART_PAUSE = 600  # после неудачной генерации не продаём AI-арт 10 минут
_art_state = {'down_until': 0.0}


def art_available():
    configured = bool(GEMINI_API_KEY or (CF_ACCOUNT_ID and CF_API_TOKEN))
    return configured and time.time() >= _art_state['down_until']


async def gemini_generate_image(prompt: str):
    if not GEMINI_API_KEY:
        return None
    url = ('https://generativelanguage.googleapis.com/v1beta/models/'
           f'{GEMINI_IMAGE_MODEL}:generateContent')
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(url, headers={'x-goog-api-key': GEMINI_API_KEY}, json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}
            })
        if r.status_code != 200:
            log.warning(f'gemini {GEMINI_IMAGE_MODEL}: HTTP {r.status_code} {r.text[:300]}')
            return None
        for cand in r.json().get('candidates', []):
            for part in (cand.get('content') or {}).get('parts', []):
                inline = part.get('inlineData') or part.get('inline_data')
                if inline and inline.get('data'):
                    return base64.b64decode(inline['data'])
        log.warning('gemini: ответ без картинки')
    except Exception as e:
        log.warning(f'gemini: {e}')
    return None


async def cloudflare_generate_image(prompt: str):
    if not (CF_ACCOUNT_ID and CF_API_TOKEN):
        return None
    url = (f'https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}'
           '/ai/run/@cf/black-forest-labs/flux-1-schnell')
    try:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(url, headers={'Authorization': f'Bearer {CF_API_TOKEN}'},
                             json={'prompt': prompt, 'steps': 8})
        if r.status_code != 200:
            log.warning(f'cloudflare flux: HTTP {r.status_code} {r.text[:300]}')
            return None
        return base64.b64decode(r.json()['result']['image'])
    except Exception as e:
        log.warning(f'cloudflare flux: {e}')
    return None


async def generate_image(prompt: str):
    img = await gemini_generate_image(prompt) or await cloudflare_generate_image(prompt)
    # генератор не работает (нет квоты/ключа) — временно не берём звёзды за AI-арт
    _art_state['down_until'] = 0.0 if img else time.time() + ART_PAUSE
    return img


async def webapp_button(user_id, username=''):
    """Кнопка Mini App: коллекция пользователя упакована в ссылку (#d=base64url JSON)."""
    gifts = await storage.gifts_list(user_id)
    data = {
        'u': username or '',
        'r': round(await markets.ton_rub(), 2),
        'e': epic_gift_link(),
        'g': [[g['slug'], g['name'], g['number'], round(g['last_price_ton'] or 0, 2)] for g in gifts[:WEBAPP_MAX_GIFTS]],
    }
    packed = base64.urlsafe_b64encode(json.dumps(data, separators=(',', ':')).encode()).decode().rstrip('=')
    return InlineKeyboardButton(text='📱 Открыть приложение', web_app=WebAppInfo(url=f'{WEBAPP_URL}#d={packed}'))


async def main_kb(user):
    return InlineKeyboardMarkup(inline_keyboard=[
        [await webapp_button(user.id, user.username)],
        [InlineKeyboardButton(text='Добавить подарок', callback_data='add_gift')],
        [InlineKeyboardButton(text='Моё портфолио', callback_data='portfolio')],
        [InlineKeyboardButton(text='Бесплатный кейс Epic Gift', url=epic_gift_link())],
        [InlineKeyboardButton(text='xRocket P2P (продать подарки)', url=xrocket_link())],
        [InlineKeyboardButton(text='AI-арт (генерация картинок)', callback_data='art_info')],
        [InlineKeyboardButton(text='Премиум', callback_data='premium_info'),
         InlineKeyboardButton(text='Пригласить друга', callback_data='ref_show')],
        [InlineKeyboardButton(text='Канал GiftIQ News', url=CHANNEL_URL)],
    ])


WELCOME = (
    '<b>GiftIQ</b> — портфолио-трекер TG подарков\n\n'
    'Что умею:\n'
    '• Показать стоимость всей коллекции в TON и ₽\n'
    '• Отслеживать floor-цены на Portals и Tonnel\n'
    '• Генерировать карточку и анимацию для сторис\n'
    '• <b>AI-арт</b> — создавать уникальные картинки по описанию\n'
    '• Присылать уведомления о колебаниях ±10% (премиум)\n\n'
    'Бонус дня: открой БЕСПЛАТНЫЙ кейс в Epic Gift. '
    'Кейс обновляется каждые 24 часа.\n\n'
    'Начни с «Добавить подарок»'
)


@router.message(Command('start'))
async def cmd_start(m: Message, command: CommandObject):
    ref = None
    if command.args and command.args.startswith('ref'):
        try:
            ref = int(command.args[3:])
        except ValueError:
            pass
    if ref == m.from_user.id:
        ref = None
    is_new = await storage.user_upsert(
        m.from_user.id,
        m.from_user.username or '',
        m.from_user.full_name,
        ref
    )
    if is_new and ref and await storage.user_exists(ref):
        until = await storage.premium_grant(ref, REF_BONUS_DAYS)
        try:
            await m.bot.send_message(
                ref,
                f'По твоей ссылке пришёл новый друг — <b>+{REF_BONUS_DAYS} дней Premium</b>.\n'
                f'Premium активен до {time.strftime("%d.%m.%Y", time.localtime(until))}'
            )
        except Exception as e:
            log.info(f'ref notify {ref}: {e}')
    await m.answer(WELCOME, reply_markup=await main_kb(m.from_user))


@router.message(Command('help'))
async def cmd_help(m: Message):
    await m.answer(
        WELCOME + '\n\nКоманды:\n'
        '/portfolio — моя коллекция\n'
        '/makeart описание — AI-арт\n'
        '/premium — премиум',
        reply_markup=await main_kb(m.from_user)
    )


@router.callback_query(F.data == 'add_gift')
async def cb_add(c: CallbackQuery):
    await c.message.answer(
        'Пришли мне ссылку на подарок:\n'
        '<code>https://t.me/nft/SnoopDogg-471247</code>\n\n'
        'Где взять: открой подарок в своём профиле, '
        'три точки, Share, копируй ссылку'
    )
    await c.answer()


@router.message(F.text.regexp(GIFT_LINK_RE, mode='search'))
async def handle_gift_link(m: Message):
    url = re.search(GIFT_LINK_RE, m.text).group(0)
    parsed = markets.parse_gift_url(url)
    if not parsed:
        return await m.answer('Не удалось распознать ссылку')
    await storage.user_upsert(m.from_user.id, m.from_user.username or '', m.from_user.full_name)
    wait = await m.answer('Ищу цены на маркетах...')
    q = await markets.get_quotes(parsed['slug'])
    if q['prices']:
        market = min(q['prices'], key=q['prices'].get)
        price = q['prices'][market]
    else:
        price, market = 0.0, 'unknown'
    added = await storage.gift_add(
        m.from_user.id, parsed['slug'], q['name'],
        parsed['number'], price, market
    )
    if not added:
        return await wait.edit_text('Этот подарок уже в твоей коллекции. /portfolio')
    rate = await markets.ton_rub()
    if price:
        per_market = '\n'.join(
            f'• {MARKET_NAMES[mk]}: {q["prices"][mk]:.2f} TON' if mk in q['prices']
            else f'• {MARKET_NAMES[mk]}: нет лотов' for mk in MARKET_NAMES
        )
        price_text = (f'Floor: <b>{price:.2f} TON</b> (~{rub_fmt(price, rate)} ₽)\n'
                      f'{per_market}')
    else:
        price_text = 'Цена пока не найдена — обновлю автоматически, когда появятся лоты'
    await wait.edit_text(
        f'Добавил: <b>{html.escape(q["name"])} #{parsed["number"]}</b>\n'
        f'{price_text}\n\n'
        '/portfolio — моя коллекция'
    )


@router.callback_query(F.data == 'portfolio')
async def cb_portfolio(c: CallbackQuery):
    await show_portfolio(c.message, c.from_user.id)
    await c.answer()


@router.message(Command('portfolio'))
async def cmd_portfolio(m: Message):
    await show_portfolio(m, m.from_user.id)


async def show_portfolio(m, user_id):
    gifts = await storage.gifts_list(user_id)
    if not gifts:
        return await m.answer('Твоя коллекция пустая. Пришли ссылку на подарок или нажми /start → «Добавить подарок»')
    rate = await markets.ton_rub()
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    lines = ['<b>Твоя коллекция</b>\n']
    for g in gifts[:20]:
        p = g['last_price_ton'] or 0
        price = f'{p:.2f} TON' if p else 'нет цены'
        lines.append(f'• <b>{html.escape(g["name"])} #{g["number"]}</b> — {price}')
    if len(gifts) > 20:
        lines.append(f'... и ещё {len(gifts) - 20}')
    lines.append(f'\nВсего: <b>{total_ton:.2f} TON</b> (~{rub_fmt(total_ton, rate)} ₽)')
    lines.append(f'<i>Floor-цены Portals/Tonnel, курс 1 TON ≈ {rate:.0f} ₽</i>')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [await webapp_button(user_id)],
        [InlineKeyboardButton(text='Карточка (фото)', callback_data='share_card'),
         InlineKeyboardButton(text='Анимация', callback_data='share_gif')],
        [InlineKeyboardButton(text='Обновить цены', callback_data='refresh'),
         InlineKeyboardButton(text='Удалить подарок', callback_data='del_menu')],
        [InlineKeyboardButton(text='AI-арт', callback_data='art_info')],
        [InlineKeyboardButton(text='БЕСПЛАТНЫЙ кейс Epic Gift', url=epic_gift_link())],
        [InlineKeyboardButton(text='Продать на xRocket (P2P)', url=xrocket_link())],
        [InlineKeyboardButton(text='Продать на Tonnel', url=tonnel_link()),
         InlineKeyboardButton(text='Продать на MRKT', url='https://t.me/mrkt')],
    ])
    await m.answer('\n'.join(lines), reply_markup=kb)


@router.callback_query(F.data == 'refresh')
async def cb_refresh(c: CallbackQuery):
    left = REFRESH_COOLDOWN - (time.time() - _last_refresh.get(c.from_user.id, 0))
    if left > 0:
        return await c.answer(f'Цены уже обновлялись, подожди {int(left)} сек', show_alert=True)
    _last_refresh[c.from_user.id] = time.time()
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        return await c.answer('Коллекция пуста', show_alert=True)
    await c.answer('Обновляю цены...')
    await jobs.refresh_prices(None, [g['slug'] for g in gifts])
    await show_portfolio(c.message, c.from_user.id)


@router.callback_query(F.data == 'del_menu')
async def cb_del_menu(c: CallbackQuery):
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        return await c.answer('Коллекция пуста', show_alert=True)
    rows = [[InlineKeyboardButton(text=f'Удалить {g["name"]} #{g["number"]}',
                                  callback_data=f'del:{g["slug"]}')] for g in gifts[:30]]
    await c.message.answer('Какой подарок убрать из коллекции?',
                           reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await c.answer()


@router.callback_query(F.data.startswith('del:'))
async def cb_del(c: CallbackQuery):
    slug = c.data[4:]
    if await storage.gift_remove(c.from_user.id, slug):
        await c.answer('Удалено')
        await c.message.edit_text(f'Удалил {html.escape(slug)} из коллекции. /portfolio')
    else:
        await c.answer('Такого подарка уже нет', show_alert=True)


async def _collection_media(c: CallbackQuery):
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        await c.answer('Коллекция пуста', show_alert=True)
        return None
    rate = await markets.ton_rub()
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    name = c.from_user.username or c.from_user.first_name or 'anon'
    return name, gifts, total_ton, total_ton * rate, rate


@router.callback_query(F.data == 'share_card')
async def cb_share(c: CallbackQuery):
    data = await _collection_media(c)
    if not data:
        return
    name, gifts, total_ton, total_rub, _ = data
    await c.answer('Рисую карточку...')
    buf = await asyncio.to_thread(render.collection_card, name, gifts, total_ton, total_rub)
    await c.message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename='collection.png'),
        caption=f'моя коллекция TG Gifts: <b>{total_ton:.2f} TON</b>\n@giftiq_tg_bot'
    )


@router.callback_query(F.data == 'share_gif')
async def cb_share_gif(c: CallbackQuery):
    data = await _collection_media(c)
    if not data:
        return
    name, gifts, total_ton, total_rub, rate = data
    await c.answer('Генерирую анимацию...')
    buf, filename = await asyncio.to_thread(render.collection_gif, name, gifts, total_ton, total_rub, rate)
    await c.message.answer_animation(
        BufferedInputFile(buf.getvalue(), filename=filename),
        caption=f'моя коллекция TG Gifts: <b>{total_ton:.2f} TON</b>\n@giftiq_tg_bot'
    )


@router.callback_query(F.data == 'art_info')
async def cb_art_info(c: CallbackQuery):
    if not art_available():
        await c.message.answer('AI-арт временно недоступен — скоро вернём. Звёзды за него сейчас не списываются.')
        return await c.answer()
    credits = await storage.art_get(c.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f'Купить за {ART_PRICE} звёзд', callback_data='art_buy')
    ]])
    await c.message.answer(
        '<b>AI-арт</b> — уникальная картинка по твоему описанию.\n\n'
        'Подходит для сторис, аватарок, подарков друзьям.\n\n'
        f'Стоимость: <b>{ART_PRICE} звёзд</b> за одну генерацию\n'
        f'У тебя сейчас: <b>{credits}</b> генераций\n'
        'Если генерация не получится — она не спишется.\n\n'
        'После покупки — пиши:\n'
        '<code>/makeart описание картинки</code>\n\n'
        'Примеры:\n'
        '• /makeart neon diamond on dark background\n'
        '• /makeart открытка с драконом в стиле anime\n'
        '• /makeart абстрактный космос фиолетово-синий',
        reply_markup=kb
    )
    await c.answer()


@router.callback_query(F.data == 'art_buy')
async def cb_art_buy(c: CallbackQuery):
    if not art_available():
        return await c.answer('AI-арт временно недоступен', show_alert=True)
    await c.message.answer_invoice(
        title='AI-арт генерация',
        description='Одна уникальная картинка по твоему описанию',
        payload='art_credit',
        currency='XTR',
        prices=[LabeledPrice(label='AI Art', amount=ART_PRICE)]
    )
    await c.answer()


@router.message(Command('makeart'))
async def cmd_makeart(m: Message, command: CommandObject):
    prompt = (command.args or '').strip()
    if not prompt:
        return await m.answer(
            'Напиши описание после команды.\n'
            'Пример: <code>/makeart neon diamond on dark background</code>'
        )
    credits = await storage.art_get(m.from_user.id)
    if credits <= 0:
        if not art_available():
            return await m.answer('AI-арт временно недоступен.')
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f'Купить за {ART_PRICE} звёзд', callback_data='art_buy')
        ]])
        return await m.answer('У тебя 0 генераций. Купи одну за звёзды.', reply_markup=kb)
    msg = await m.answer('Генерирую картинку... (10-30 сек)')
    img = await generate_image(prompt)
    if not img:
        return await msg.edit_text(
            'Не удалось сгенерировать. Попробуй другое описание чуть позже.\n'
            'Генерация не списалась.'
        )
    if not await storage.art_use(m.from_user.id):
        return await msg.edit_text('Генерации закончились. Купи ещё через /start → AI-арт')
    left = await storage.art_get(m.from_user.id)
    await msg.delete()
    await m.answer_photo(
        BufferedInputFile(img, filename='art.png'),
        caption=(
            f'<b>AI-арт по запросу:</b>\n<i>{html.escape(prompt[:200])}</i>\n\n'
            f'Осталось генераций: {left}\n'
            f'Создано в @giftiq_tg_bot'
        )
    )


async def send_premium_info(m: Message, user_id: int):
    until = await storage.premium_get(user_id)
    status = (f'Твой Premium активен до <b>{time.strftime("%d.%m.%Y", time.localtime(until))}</b>\n\n'
              if until > time.time() else '')
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f'Купить за {PREMIUM_PRICE} звёзд', callback_data='premium_buy')
    ]])
    await m.answer(
        f'{status}<b>Premium — {PREMIUM_PRICE} звёзд/мес</b>\n\n'
        '• Push-уведомления, когда floor твоих подарков меняется на ±10%\n'
        '• Проверка цен каждые 30 минут на Portals и Tonnel\n'
        f'• За каждого приглашённого друга — +{REF_BONUS_DAYS} дней бесплатно',
        reply_markup=kb
    )


@router.callback_query(F.data == 'premium_info')
async def cb_premium_info(c: CallbackQuery):
    await send_premium_info(c.message, c.from_user.id)
    await c.answer()


@router.message(Command('premium'))
async def cmd_premium(m: Message):
    await send_premium_info(m, m.from_user.id)


@router.callback_query(F.data == 'premium_buy')
async def cb_premium_buy(c: CallbackQuery):
    await c.message.answer_invoice(
        title='GiftIQ Premium',
        description='30 дней push-уведомлений о колебаниях цен',
        payload='premium_month',
        currency='XTR',
        prices=[LabeledPrice(label='Premium', amount=PREMIUM_PRICE)]
    )
    await c.answer()


EXPECTED_PRICES = {'premium_month': lambda: PREMIUM_PRICE, 'art_credit': lambda: ART_PRICE}


@router.pre_checkout_query()
async def pcq(q: PreCheckoutQuery):
    expected = EXPECTED_PRICES.get(q.invoice_payload)
    if q.currency != 'XTR' or not expected or q.total_amount != expected():
        return await q.answer(ok=False, error_message='Счёт устарел. Открой покупку заново через /start')
    if q.invoice_payload == 'art_credit' and not art_available():
        return await q.answer(ok=False, error_message='AI-арт временно недоступен')
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def paid(m: Message):
    sp = m.successful_payment
    await storage.user_upsert(m.from_user.id, m.from_user.username or '', m.from_user.full_name)
    await storage.payment_record(m.from_user.id, sp.total_amount, sp.invoice_payload,
                                 sp.telegram_payment_charge_id)
    if sp.invoice_payload == 'premium_month':
        until = await storage.premium_grant(m.from_user.id, 30)
        await m.answer(f'Премиум активен до {time.strftime("%d.%m.%Y", time.localtime(until))}')
    elif sp.invoice_payload == 'art_credit':
        await storage.art_grant(m.from_user.id, 1)
        credits = await storage.art_get(m.from_user.id)
        await m.answer(
            f'Генерация добавлена. У тебя {credits} AI-арт генераций.\n\n'
            'Используй: <code>/makeart описание</code>'
        )


@router.callback_query(F.data == 'ref_show')
async def cb_ref(c: CallbackQuery):
    me = await c.bot.me()
    link = f'https://t.me/{me.username}?start=ref{c.from_user.id}'
    await c.message.answer(
        f'<b>Твоя реф-ссылка</b>:\n<code>{link}</code>\n\n'
        f'За каждого нового друга, который запустит бота по ссылке — <b>+{REF_BONUS_DAYS} дней Premium</b>'
    )
    await c.answer()


@router.message(Command('stats'))
async def cmd_stats(m: Message):
    if m.from_user.id != ADMIN_USER_ID:
        return
    s = await storage.stats_get()
    await m.answer(
        f'Статистика:\n'
        f'Юзеров: {s["users"]}\n'
        f'Премиум: {s["premium"]}\n'
        f'Stars 24ч: {s["stars_24h"]}\n'
        f'Подарков в базе: {s["gifts"]}'
    )


@router.message(F.text & ~F.text.startswith('/'))
async def fallback_text(m: Message):
    await m.answer(
        'Пришли ссылку на подарок вида\n<code>https://t.me/nft/SnoopDogg-471247</code>\n\n'
        'или открой меню: /start',
    )


@router.errors()
async def on_error(event: ErrorEvent):
    log.exception(f'ошибка в обработчике: {event.exception}', exc_info=event.exception)
    upd = event.update
    try:
        if upd.callback_query:
            await upd.callback_query.answer('Что-то пошло не так, попробуй ещё раз', show_alert=True)
        elif upd.message:
            await upd.message.answer('Что-то пошло не так, попробуй ещё раз чуть позже')
    except Exception:
        pass
