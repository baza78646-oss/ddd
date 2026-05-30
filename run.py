import asyncio
import threading
import logging
from dotenv import load_dotenv

load_dotenv()

from aggregator import start_aggregator
from bot import dp, bot
from db import init_db, get_expiring_users, set_notified_3_days

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def check_expirations():
    while True:
        try:
            users = get_expiring_users()
            for user in users:
                telegram_id = user['telegram_id']
                expires_at_str = user['expires_at']
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=f"Внимание! Ваша подписка на VPN истекает через 3 дня ({expires_at_str}).\nПожалуйста, продлите её, чтобы не потерять доступ."
                    )
                    logging.info(f"Sent 3-day reminder to {telegram_id}")
                except Exception as e:
                    logging.error(f"Failed to send reminder to {telegram_id}: {e}")
                finally:
                    set_notified_3_days(telegram_id, True)
        except Exception as e:
            logging.error(f"Error in check_expirations task: {e}")

        await asyncio.sleep(3600)  # Check every hour

async def main():
    init_db()

    # Start aggregator in a background thread
    agg_thread = threading.Thread(target=start_aggregator, args=(8080,), daemon=True)
    agg_thread.start()

    logging.info("Starting Telegram Bot...")

    # Run expiration check in background
    asyncio.create_task(check_expirations())

    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down...")
