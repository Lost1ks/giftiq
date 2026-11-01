import time, re
from aiogram import Router, F, Bot
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, LabeledPrice, PreCheckoutQuery,
                           BufferedInputFile)
from aiogram.filters import Command, CommandObject

from config import BOT_TOKEN, ADMIN_USER_ID, TONNEL_REF, PREMIUM_PRICE, RUB_PER_TON
import storage
import markets
import render

router = Router()

def tonnel_link(slug=None):
    base = 'https://t.me/tonnel_network_bot'
    if TONNEL_REF:
        return f'{base}?start=ref_{TONNEL_REF}'
    return base

@router.message(Command('start'))
async def cmd_start(m: Message, command: CommandObject):
    ref = None
    if command.args and command.args.startswith('ref'):
        try: ref = int(command.args[3:])
        except: pass
    await storage.user_upsert(
        m.from_user.id, m.from_user.username or '',
        m.from_user.full_name, ref
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='➕ Добавить подарок', callback_data='add_gift')],
        [InlineKeyboardButton(text='📊 Моё портфолио', callback_data='portfolio')],
        [InlineKeyboardButton(text='💎 Премиум', callback_data='premium_info')],
        [InlineKeyboardButton(text='👥 Пригласить друга', callback_data='ref_show')],
    ])
    await m.answer(
        '💎 <b>GiftIQ</b> — твой портфолио-трекер TG подарков\n\n'
        '🎯 Что умею:\n'
        '• Показать стоимость всей коллекции\n'
        '• Отслеживать цены на tonnel / mrkt\n'
        '• Генерировать красивую карточку для сторис\n'
        '• Присылать уведомления о колебаниях (премиум)\n\n'
        '👉 Начни с кнопки <b>«Добавить подарок»</b>',
        reply_markup=kb, parse_mode='HTML'
    )

@router.callback_query(F.data == 'add_gift')
async def cb_add(c: CallbackQuery):
    await c.message.answer(
        '📩 Пришли мне <b>ссылку на подарок</b> в формате:\n'
        '<code>https://t.me/nft/SnoopDogg-471247</code>\n\n'
        'Где взять: открой подарок в своём профиле TG → '
        'нажми три точки → <b>Share</b> → копируй ссылку\n\n'
        'Или просто кинь мне ссылку любого подарка который хочешь трекать',
        parse_mode='HTML'
    )
    await c.answer()

@router.message(F.text.regexp(r'https?://t\.me/nft/[A-Za-z0-9]+-\d+'))
async def handle_gift_link(m: Message):
    url_match = re.search(r'https?://t\.me/nft/[A-Za-z0-9]+-\d+', m.text)
    url = url_match.group(0)
    parsed = await markets.parse_gift_url(url)
    if not parsed:
        return await m.answer('❌ не удалось распарсить ссылку')
    await m.answer('⏳ ищу цены на маркетах...')
    price, market = await markets.get_floor(parsed['slug'].split('-')[0])
    if not price:
        price, market = 0.0, 'unknown'
    added = await storage.gift_add(
        m.from_user.id, parsed['slug'], parsed['name'],
        parsed['number'], price, market
    )
    if not added:
        return await m.answer('ℹ️ этот подарок уже в твоей коллекции')
    price_text = f'{price:.2f} TON (~{price*RUB_PER_TON:,.0f} ₽)' if price else 'цена не найдена'
    await m.answer(
        f'✅ добавил: <b>{parsed["name"]} #{parsed["number"]}</b>\n'
        f'💰 текущая floor: {price_text}\n'
        f'🏪 источник: {market}\n\n'
        '/portfolio — моя коллекция',
        parse_mode='HTML'
    )

@router.callback_query(F.data == 'portfolio')
async def cb_portfolio(c: CallbackQuery):
    await show_portfolio(c.message, c.from_user.id)
    await c.answer()

@router.message(Command('portfolio'))
async def cmd_portfolio(m: Message):
    await show_portfolio(m, m.from_user.id)

async def show_portfolio(m: Message, user_id: int):
    gifts = await storage.gifts_list(user_id)
    if not gifts:
        return await m.answer(
            '🫙 твоя коллекция пустая.\n\n'
            'нажми /start → «Добавить подарок»'
        )
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    total_rub = total_ton * RUB_PER_TON
    lines = ['💎 <b>твоя коллекция</b>\n']
    for g in gifts[:20]:
        p = g['last_price_ton'] or 0
        lines.append(f'• <b>{g["name"]} #{g["number"]}</b> — {p:.2f} TON')
    if len(gifts) > 20:
        lines.append(f'... и ещё {len(gifts) - 20}')
    lines.append(f'\n📊 всего: <b>{total_ton:.2f} TON</b> (~{total_rub:,.0f} ₽)')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📸 Карточка для сторис', callback_data='share_card')],
        [InlineKeyboardButton(text='🛒 Продать на tonnel', url=tonnel_link())],
    ])
    await m.answer('\n'.join(lines).replace(',', ' '),
                   parse_mode='HTML', reply_markup=kb)

@router.callback_query(F.data == 'share_card')
async def cb_share(c: CallbackQuery):
    gifts = await storage.gifts_list(c.from_user.id)
    if not gifts:
        return await c.answer('коллекция пуста', show_alert=True)
    total_ton = sum(g['last_price_ton'] or 0 for g in gifts)
    total_rub = total_ton * RUB_PER_TON
    buf = render.collection_card(
        c.from_user.username or 'anon', gifts, total_ton, total_rub
    )
    await c.message.answer_photo(
        BufferedInputFile(buf.getvalue(), filename='collection.png'),
        caption=f'💎 моя коллекция TG Gifts: <b>{total_ton:.2f} TON</b>\n'
                f'трекер: @giftiq_tg_bot',
        parse_mode='HTML'
    )
    await c.answer()

@router.callback_query(F.data == 'premium_info')
async def cb_premium_info(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f'💎 Купить за {PREMIUM_PRICE}⭐',
                             callback_data='premium_buy')
    ]])
    await c.message.answer(
        f'💎 <b>Premium — {PREMIUM_PRICE}⭐/мес</b>\n\n'
        '• 🔔 push о колебаниях ±10%\n'
        '• 📊 расширенная аналитика редкости\n'
        '• 💡 AI-инсайты по рынку\n'
        '• 📄 PDF-отчёт портфолио\n'
        '• 🎯 алерты по целевой цене',
        parse_mode='HTML', reply_markup=kb
    )
    await c.answer()

@router.callback_query(F.data == 'premium_buy')
async def cb_premium_buy(c: CallbackQuery):
    await c.message.answer_invoice(
        title='GiftIQ Premium',
        description='Месяц безлимитных функций + push уведомления',
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
        await m.answer(
            f'✅ <b>премиум активен</b> до '
            f'{time.strftime("%d.%m.%Y", time.localtime(until))}',
            parse_mode='HTML'
        )

@router.callback_query(F.data == 'ref_show')
async def cb_ref(c: CallbackQuery):
    me = await c.bot.me()
    link = f'https://t.me/{me.username}?start=ref{c.from_user.id}'
    await c.message.answer(
        f'👥 <b>твоя реф-ссылка</b>:\n<code>{link}</code>\n\n'
        'за каждого приглашённого друга — <b>+7 дней Premium</b>',
        parse_mode='HTML'
    )
    await c.answer()

@router.message(Command('stats'))
async def cmd_stats(m: Message):
    if m.from_user.id != ADMIN_USER_ID:
        return
    s = await storage.stats_get()
    await m.answer(
        f'📊 статистика:\n'
        f'👥 юзеров: {s["users"]}\n'
        f'💎 премиум: {s["premium"]}\n'
        f'⭐ stars 24ч: {s["stars_24h"]}\n'
        f'🎁 подарков в базах: {s["gifts"]}'
    )