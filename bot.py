import os
import uuid
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton

import db
from xui_api import XUIClient

logger = logging.getLogger(__name__)

bot = Bot(token=os.environ.get("BOT_TOKEN", "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"))
dp = Dispatcher()

# Price in Telegram Stars (XTR)
VPN_PRICE = 50

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить VPN ⭐️", callback_data="buy_vpn")]
    ])
    await message.answer(
        "Добро пожаловать! Нажмите кнопку ниже, чтобы купить подписку на VPN.",
        reply_markup=kb
    )

@dp.callback_query(F.data == "buy_vpn")
async def process_buy_vpn(callback_query: types.CallbackQuery):
    await callback_query.answer()

    prices = [LabeledPrice(label="VPN Subscription (1 Month)", amount=VPN_PRICE)]

    await bot.send_invoice(
        chat_id=callback_query.from_user.id,
        title="VPN Subscription",
        description="Premium VPN Access (DE + NL servers)",
        payload="vpn_1_month",
        provider_token="",  # Empty for Telegram Stars
        currency="XTR",
        prices=prices,
        start_parameter="vpn-sub"
    )

@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id

    # Check if user already exists
    user = db.get_user(user_id)
    if user:
        sub_id = user['sub_id']
        logger.info(f"User {user_id} already has sub_id {sub_id}, renewing/re-sending.")
    else:
        sub_id = str(uuid.uuid4())
        # We need an email identifier for the panel
        email = f"tg_{user_id}_{sub_id[:8]}"
        client_uuid = str(uuid.uuid4())

        de_client = XUIClient(
            os.environ.get("DE_PANEL_URL"),
            os.environ.get("DE_USERNAME"),
            os.environ.get("DE_PASSWORD")
        )
        nl_client = XUIClient(
            os.environ.get("NL_PANEL_URL"),
            os.environ.get("NL_USERNAME"),
            os.environ.get("NL_PASSWORD")
        )

        de_inbounds = de_client.get_inbounds()
        nl_inbounds = nl_client.get_inbounds()

        # Add to the first inbound found
        if de_inbounds:
            de_client.add_client(de_inbounds[0]['id'], email, sub_id, client_uuid)
        else:
            logger.error("No inbounds found on DE server")

        if nl_inbounds:
            nl_client.add_client(nl_inbounds[0]['id'], email, sub_id, client_uuid)
        else:
            logger.error("No inbounds found on NL server")

        db.create_user(user_id, sub_id)

    aggregator_url = os.environ.get("AGGREGATOR_URL", "http://localhost:8080").rstrip('/')
    final_link = f"{aggregator_url}/sub/{sub_id}"

    await message.answer(
        f"✅ Оплата прошла успешно!\n\nВаша ссылка для подписки:\n`{final_link}`\n\n"
        "Скопируйте эту ссылку и вставьте в Hiddify. Серверы подтянутся автоматически.",
        parse_mode="Markdown"
    )
