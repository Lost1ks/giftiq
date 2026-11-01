import asyncio, logging, pathlib
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
import storage
import handlers
import jobs

pathlib.Path('.').mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s'
)

async def main():
    await storage.init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(handlers.router)
    sched = jobs.setup_scheduler(bot)
    sched.start()
    logging.info('GiftIQ запущен')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())