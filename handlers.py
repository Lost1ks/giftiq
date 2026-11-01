import time
import re

from aiogram import Router, F
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery,
                           BufferedInputFile)
from aiogram.filters import Command, CommandObject

from config import (ADMIN_USER_ID, TONNEL_REF, EPIC_GIFT_REF, XROCKET_REF,
                    PREMIUM_PRICE, RUB_PER_TON)
import storage
import markets
import render

router = Router()


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


@router.message(Command('start'))
async def cmd_start(m: Message, command: CommandObject):
    ref = None
    if command.args and command.args.startswith('ref'):
        try:
            ref = int(command.args[3:])
        except Exception:
            pass
    await storage.user_upsert(
        m.from_user.id,
        m.from_user.username or '',
        m.from_user.full_name,
        ref
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Добавить подарок', callback_data='add_gift')],
        [InlineKeyboardButton(text='Моё портфолио', callback_data='portfolio')],
        [InlineKeyboardButton(text='Бесплатный кейс Epic Gift', url=epic_gift_link())],
        [InlineKeyboardButton(text='xRocket P2P (продать подарки)', url=xrocket_link())],
        [InlineKeyboardButton(text='Премиум', callback_data='premium_info')],
        [InlineKeyboardButton(text='Пригласить друга', callback_data='ref_show')],
    ])
    await m.answer(
        '<b>GiftIQ</b> — портфолио-трекер TG подарков\n\n'
        'Что умею:\n'
        '• Показать стоимость всей коллекции\n'
        '• Отслеживать цены на tonnel и mrkt\n'
        '• Генерировать карточку и анимацию для сторис\n'
        '• Присылать уведомления о колебаниях (премиум)\n\n'
        'Бонус дня: открой БЕСПЛАТНЫЙ кейс в Epic Gift. '
        'Реальные NFT подарки TON сразу на твой кошелёк.\n\n'
        'Кейс обновляется каждые 24 часа. Приходи каждый день.\n\n'
        'Начни с «Добавить подарок»',
        reply_markup=kb
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


@router.message(F.text.regexp(r'https?://t\.me/nft/[A-Za-z0-9]+-\d+'))
async def handle_gift_link(m: Message):
    url_match = re.search(r'https?://t\.me/nft/[A-Za-z0-9]+-\d+', m.text)
    url = url_match.group(0)
    parsed = markets.parse_gift_url(url)
    if not parsed:
        return await m.answer('Не удалось распарсить ссылку')
    await m.answer('Ищу цены на маркетах...')
    price, market = await markets.get_floor(parsed['slug'].split('-')[0])
    if not price:
        price, market = 0.0, 'unknown'
    added = await storage.gift_add(
        m.from_user.id, parsed['slug'], parsed['name'],
        parsed['number'], price, market
    )
    if not added:
        return await m.answer('Этот подарок уже в твоей коллекции')
    if price:
        rub = int(price * RUB_PER_TON)
        price_text = f'{price:.2f} TON (~{rub} rub)'
    else:
        price_text = 'цена не найдена'
    await m.answer(
        f'Добавил: <b>{parsed["name"]} #{parsed["number"]}</b>\n'
        f'Floor: {price_text}\n'
        f'Источник: {market}\n\n'
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
        return await m.answer('Твоя коллекция пустая. /start → «Добавить подарок»')
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    total_rub = total_ton * RUB_PER_TON
    lines = ['<b>Твоя коллекция</b>\n']
    for g in gifts[:20]:
        p = g['last_price_ton'] or 0
        lines.append(f'• <b>{g["name"]} #{g["number"]}</b> — {p:.2f} TON')
    if len(gifts) > 20:
        lines.append(f'... и ещё {len(gifts) - 20}')
    rub_s = f'{int(total_rub):,}'.replace(',', ' ')
    lines.append(f'\nВсего: <b>{total_ton:.2f} TON</b> (~{rub_s} rub)')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Карточка (фото)', callback_data='share_card'),
         InlineKeyboardButton(text='Анимация', callback_data='share_gif')],
        [InlineKeyboardButton(text='БЕСПЛАТНЫЙ кейс Epic Gift', url=epic_gift_link())],
        [InlineKeyboardButton(text='Продать на xRocket (P2P)', url=xrocket_link())],
        [InlineKeyboardButton(text='Продать на MRKT', url='https://t.me/mrkt')],
    ])
    await m.answer('\n'.join(lines), reply_markup=kb)


@router.callback_query(F.data == 'share_card')
async def cb_share(c: CallbackQuery):
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        return await c.answer('Коллекция пуста', show_alert=True)
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    total_rub = total_ton * RUB_PER_TON
    buf = render.collection_card(
        c.from_user.username or 'anon', gifts, total_ton, total_rub
    )
    await c.message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename='collection.png'),
        caption=f'моя коллекция TG Gifts: <b>{total_ton:.2f} TON</b>\n@giftiq_tg_bot'
    )
    await c.answer()


@router.callback_query(F.data == 'share_gif')
async def cb_share_gif(c: CallbackQuery):
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        return await c.answer('Коллекция пуста', show_alert=True)
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    total_rub = total_ton * RUB_PER_TON
    await c.answer('Генерирую анимацию...')
    buf = render.collection_gif(
        c.from_user.username or 'anon', gifts, total_ton, total_rub
    )
    await c.message.answer_animation(
        BufferedInputFile(buf.getvalue(), filename='collection.gif'),
        caption=f'моя коллекция TG Gifts: <b>{total_ton:.2f} TON</b>\n@giftiq_tg_bot'
    )


@router.callback_query(F.data == 'premium_info')
async def cb_premium_info(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f'Купить за {PREMIUM_PRICE} звёзд', callback_data='premium_buy')
    ]])
    await c.message.answer(
        f'<b>Premium — {PREMIUM_PRICE} звёзд/мес</b>\n\n'
        '• Push о колебаниях ±10%\n'
        '• Расширенная аналитика редкости\n'
        '• AI-инсайты\n'
        '• PDF-отчёт\n'
        '• Алерты по целевой цене',
        reply_markup=kb
    )
    await c.answer()


@router.callback_query(F.data == 'premium_buy')
async def cb_premium_buy(c: CallbackQuery):
    await c.message.answer_invoice(
        title='GiftIQ Premium',
        description='Месяц безлимитных функций + push',
        payload='premium_month',
        currency='XTR',
        prices=[LabeledPrice(label='Premium', amount=PREMIUM_PRICE)]
    )
    await c.answer()


@router.pre_checkout_query()
async def pcq(q: PreCheckoutQuery):
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def paid(m: Message):
    sp = m.successful_payment
    await storage.payment_record(m.from_user.id, sp.total_amount, sp.invoice_payload)
    if sp.invoice_payload == 'premium_month':
        until = await storage.premium_grant(m.from_user.id, 30)
        await m.answer(f'Премиум активен до {time.strftime("%d.%m.%Y", time.localtime(until))}')


@router.callback_query(F.data == 'ref_show')
async def cb_ref(c: CallbackQuery):
    me = await c.bot.me()
    link = f'https://t.me/{me.username}?start=ref{c.from_user.id}'
    await c.message.answer(
        f'<b>Твоя реф-ссылка</b>:\n<code>{link}</code>\n\n'
        'За каждого приглашённого друга — <b>+7 дней Premium</b>'
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
