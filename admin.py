"""Админ: свои посты в канал по расписанию (/newpost, /posts), тестовый автопост (/post)."""
import datetime
import re

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_USER_ID
import jobs
import storage

router = Router()
MSK = datetime.timezone(datetime.timedelta(hours=3))
WHEN_HINT = ('Когда опубликовать? Время московское, напиши например:\n'
             '<code>сейчас</code>\n<code>18:30</code> — сегодня (или завтра, если время прошло)\n'
             '<code>завтра 10:00</code>\n<code>05.11 18:30</code>\n\n/cancel — отмена')


class NewPost(StatesGroup):
    content = State()
    when = State()
    confirm = State()


def is_admin(user_id):
    return ADMIN_USER_ID and user_id == ADMIN_USER_ID


def fmt(ts):
    return datetime.datetime.fromtimestamp(ts, MSK).strftime('%d.%m %H:%M')


def parse_when(text, now=None):
    """'сейчас' / '18:30' / 'завтра 18:30' / '05.11 18:30' / '05.11.2026 18:30' -> datetime (МСК) или None"""
    now = now or datetime.datetime.now(MSK)
    t = ' '.join(text.strip().lower().split())
    if t in ('сейчас', 'now', 'щас'):
        return now
    m = re.fullmatch(r'(?:(завтра)\s+|(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\s+)?(\d{1,2}):(\d{2})', t)
    if not m:
        return None
    tomorrow, day, month, year, hh, mm = m.groups()
    try:
        if day:
            y = int(year) + (2000 if year and len(year) == 2 else 0) if year else now.year
            dt = datetime.datetime(y, int(month), int(day), int(hh), int(mm), tzinfo=MSK)
        else:
            dt = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
            if tomorrow or dt <= now:
                dt += datetime.timedelta(days=1)
    except ValueError:
        return None
    return dt


@router.message(Command('myid'))
async def cmd_myid(m: Message):
    await m.answer(f'Твой Telegram ID: <code>{m.from_user.id}</code>')


@router.message(Command('cancel'), StateFilter('*'))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer('Отменено.')


@router.message(Command('newpost'))
async def cmd_newpost(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return await m.answer('Команда только для админа бота.\n'
                              f'Твой ID: <code>{m.from_user.id}</code> — его нужно указать в ADMIN_USER_ID на хостинге.')
    await state.set_state(NewPost.content)
    await m.answer(f'Пришли пост для канала {jobs.CHANNEL} ровно так, как он должен выглядеть: '
                   'текст (жирный, ссылки — всё сохранится), фото или видео с подписью.\n\n/cancel — отмена')


@router.message(NewPost.content)
async def np_content(m: Message, state: FSMContext):
    if m.text and m.text.startswith('/'):
        return await m.answer('Пришли сам пост (не команду) или /cancel')
    await state.update_data(chat=m.chat.id, msg=m.message_id)
    await state.set_state(NewPost.when)
    await m.answer(WHEN_HINT)


@router.message(NewPost.when)
async def np_when(m: Message, state: FSMContext):
    dt = parse_when(m.text or '')
    now = datetime.datetime.now(MSK)
    if not dt:
        return await m.answer('Не понял время.\n\n' + WHEN_HINT)
    if dt < now - datetime.timedelta(minutes=1):
        return await m.answer('Это время уже прошло. Напиши другое.')
    await state.update_data(post_at=int(dt.timestamp()))
    await state.set_state(NewPost.confirm)
    when = 'сразу' if dt <= now + datetime.timedelta(minutes=1) else f'{dt:%d.%m в %H:%M} МСК'
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Запланировать', callback_data='np_ok'),
        InlineKeyboardButton(text='Отмена', callback_data='np_no'),
    ]])
    await m.answer(f'Пост выше будет опубликован в {jobs.CHANNEL} {when}. Всё верно?', reply_markup=kb)


@router.callback_query(NewPost.confirm, F.data.in_({'np_ok', 'np_no'}))
async def np_confirm(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    if c.data == 'np_no':
        await c.message.edit_text('Отменено.')
        return await c.answer()
    post_id = await storage.sched_add(data['chat'], data['msg'], data['post_at'])
    await c.message.edit_text(f'Пост #{post_id} запланирован на {fmt(data["post_at"])} МСК.\n'
                              'Не удаляй сообщение с постом до публикации. Все посты: /posts')
    await c.answer()
    await jobs.publish_scheduled(c.bot)   # если время «сейчас» — публикуем сразу


@router.message(Command('posts'))
async def cmd_posts(m: Message):
    if not is_admin(m.from_user.id):
        return
    rows = await storage.sched_list()
    if not rows:
        return await m.answer('Запланированных постов нет. Новый: /newpost')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'#{pid} · {fmt(ts)} · показать', callback_data=f'sp_show:{pid}'),
         InlineKeyboardButton(text='Удалить', callback_data=f'sp_del:{pid}')]
        for pid, _, _, ts in rows[:30]
    ])
    auto = 'включены (10:05, 18:05, 22:05 МСК)' if jobs.AUTO_POSTS else 'выключены'
    await m.answer(f'Запланировано постов: {len(rows)}\nАвтопосты: {auto}', reply_markup=kb)


@router.callback_query(F.data.startswith('sp_'))
async def cb_sched(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        return await c.answer()
    action, pid = c.data.split(':')
    pid = int(pid)
    if action == 'sp_del':
        ok = await storage.sched_set_status(pid, 'cancelled')
        return await c.answer('Удалено' if ok else 'Этот пост уже не в очереди', show_alert=not ok)
    row = next((r for r in await storage.sched_list() if r[0] == pid), None)
    if not row:
        return await c.answer('Этот пост уже не в очереди', show_alert=True)
    await c.answer()
    try:
        await c.bot.copy_message(c.from_user.id, row[1], row[2])
    except Exception as e:
        await c.message.answer(f'Не могу показать пост #{pid}: {e}')


@router.message(Command('post'))
async def cmd_post(m: Message):
    """Опубликовать следующий автопост прямо сейчас (проверка, что бот может писать в канал)."""
    if not is_admin(m.from_user.id):
        return
    ok, info = await jobs.post_to_channel(m.bot)
    await m.answer(f'Автопост опубликован ({info})' if ok else f'Не получилось: {info}')
