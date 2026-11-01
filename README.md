\# GiftIQ — Portfolio Tracker TG Gifts



\## Запуск

1\. ENV: BOT\_TOKEN, ADMIN\_USER\_ID, TON\_ADDRESS, TONNEL\_REF (опц.), DB\_PATH=giftiq.db

2\. pip install -r requirements.txt

3\. python main.py



\## Структура

main.py — entry point

handlers.py — команды и колбеки бота

jobs.py — фоновое обновление цен

markets.py — tonnel/mrkt API

storage.py — SQLite

render.py — PNG карточка

config.py — читает ENV

