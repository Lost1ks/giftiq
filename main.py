import asyncio, logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import BOT_TOKEN
import storage
import admin
import handlers
import jobs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

COMMANDS = [
    BotCommand(command='start', description='Меню'),
    BotCommand(command='portfolio', description='Моя коллекция'),
    BotCommand(command='makeart', description='AI-арт по описанию'),
    BotCommand(command='premium', description='Премиум и уведомления'),
    BotCommand(command='help', description='Помощь'),
]


async def main():
    await storage.init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(admin.router)   # раньше handlers: шаги /newpost не должны попадать в общие обработчики
    dp.include_router(handlers.router)
    try:
        await bot.set_my_commands(COMMANDS)
    except Exception as e:
        logging.warning(f'set_my_commands: {e}')
    sched = jobs.setup_scheduler(bot)
    sched.start()
    logging.info('GiftIQ запущен')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
