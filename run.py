import asyncio
import threading
import logging
from dotenv import load_dotenv

load_dotenv()

from aggregator import start_aggregator
from bot import dp, bot
from db import init_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def main():
    init_db()

    # Start aggregator in a background thread
    agg_thread = threading.Thread(target=start_aggregator, args=(8080,), daemon=True)
    agg_thread.start()

    logging.info("Starting Telegram Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down...")
