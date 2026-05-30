import os
import uuid
import datetime
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import db
from xui_api import XUIClient
from payments import create_yookassa_payment, check_yookassa_payment, create_cryptomus_payment, check_cryptomus_payment

class GiftSub(StatesGroup):
    waiting_for_username = State()

logger = logging.getLogger(__name__)

bot = Bot(token=os.environ.get("BOT_TOKEN", "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"))
dp = Dispatcher()

PLANS = {
    "trial": {"name": "3 дня (Пробный)", "days": 3, "price": 0},
    "1m": {"name": "1 месяц", "days": 30, "price": 150},
    "3m": {"name": "3 месяца", "days": 90, "price": 400},
    "6m": {"name": "6 месяцев", "days": 180, "price": 700},
    "1y": {"name": "1 год", "days": 365, "price": 1200}
}

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()

    if command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("_")[1])
            if referrer_id != message.from_user.id:
                db.add_referral(message.from_user.id, referrer_id)
        except ValueError:
            pass

    user = db.get_user(message.from_user.id)
    if not user:
        db.create_user(message.from_user.id, str(uuid.uuid4()), str(uuid.uuid4()), expires_at=datetime.datetime.now(), username=message.from_user.username)
    elif message.from_user.username:
        db.update_username(message.from_user.id, message.from_user.username)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", callback_data="buy_sub")],
        [InlineKeyboardButton(text="❤️ Пригласить друзей", callback_data="invite_friends")],
        [InlineKeyboardButton(text="🎁 Подарить подписку", callback_data="gift_sub")],
        [InlineKeyboardButton(text="🆘 Помощь", callback_data="help_btn")]
    ])
    await message.answer(
        "Добро пожаловать! Выберите действие:",
        reply_markup=kb
    )

@dp.callback_query(F.data == "buy_sub")
async def process_buy_sub(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    buttons = []
    for plan_id, plan in PLANS.items():
        if plan_id == "trial":
            buttons.append([InlineKeyboardButton(text=f"{plan['name']} — Бесплатно", callback_data=f"plan_{plan_id}")])
        else:
            buttons.append([InlineKeyboardButton(text=f"{plan['name']} — {plan['price']} руб", callback_data=f"plan_{plan_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.answer(
        "Выберите тарифный план для покупки подписки на VPN.",
        reply_markup=kb
    )

@dp.callback_query(F.data == "invite_friends")
async def process_invite_friends(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{callback_query.from_user.id}"
    await callback_query.message.answer(
        f"Ваша реферальная ссылка:\n`{ref_link}`\n\n"
        "За каждого приглашённого друга, который купит подписку, вы получите 10 дней бесплатно!",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "help_btn")
async def process_help_btn(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    await callback_query.message.answer(
        "🆘 **Помощь и инструкции**\n\n"
        "1. Скачайте приложение Hiddify (доступно в App Store и Google Play).\n"
        "2. Скопируйте ссылку, которую вам выдал бот после оплаты.\n"
        "3. Откройте Hiddify, нажмите '+' и выберите 'Добавить из буфера обмена'.\n"
        "4. Нажмите кнопку 'Подключить'.\n\n"
        "Если у вас возникли проблемы, напишите в поддержку: @support",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "gift_sub")
async def process_gift_sub_start(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.set_state(GiftSub.waiting_for_username)
    await callback_query.message.answer("Введите username друга (например, @username):")

@dp.message(GiftSub.waiting_for_username)
async def process_gift_username(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip("@")
    target_user = db.get_user_by_username(username)

    if not target_user:
        await message.answer("Пользователь не найден в базе. Убедитесь, что он запускал бота.")
        await state.clear()
        return

    await state.update_data(target_telegram_id=target_user['telegram_id'])
    await state.set_state(None)

    buttons = []
    for plan_id, plan in PLANS.items():
        if plan_id != "trial":
            buttons.append([InlineKeyboardButton(text=f"{plan['name']} — {plan['price']} руб", callback_data=f"giftplan_{plan_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"Вы дарите подписку пользователю @{username}. Выберите тарифный план:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("giftplan_"))
async def process_gift_plan_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    plan_id = callback_query.data.split("_")[1]
    plan = PLANS[plan_id]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить криптой (Cryptomus)", callback_data=f"giftpay_cryptomus_{plan_id}")],
        [InlineKeyboardButton(text="Оплатить картой (ЮКасса)", callback_data=f"giftpay_yookassa_{plan_id}")]
    ])
    await callback_query.message.answer(
        f"Вы выбрали тариф в подарок: {plan['name']}. Сумма к оплате: {plan['price']} руб.\nВыберите способ оплаты:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback_query: types.CallbackQuery):
    await callback_query.answer()
    plan_id = callback_query.data.split("_")[1]
    plan = PLANS[plan_id]
    user_id = callback_query.from_user.id

    if plan_id == "trial":
        user = db.get_user(user_id)
        if user and user['trial_used']:
            await callback_query.message.answer("Вы уже использовали пробный период.")
            return

        await process_successful_subscription(callback_query.message, user_id, plan['days'])
        db.set_trial_used(user_id)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить криптой (Cryptomus)", callback_data=f"pay_cryptomus_{plan_id}")],
        [InlineKeyboardButton(text="Оплатить картой (ЮКасса)", callback_data=f"pay_yookassa_{plan_id}")]
    ])
    await callback_query.message.answer(
        f"Вы выбрали тариф: {plan['name']}. Сумма к оплате: {plan['price']} руб.\nВыберите способ оплаты:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("pay_") | F.data.startswith("giftpay_"))
async def process_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = callback_query.data.split("_")

    is_gift = data[0] == "giftpay"
    method = data[1]
    plan_id = data[2]
    plan = PLANS[plan_id]

    target_telegram_id = None
    if is_gift:
        state_data = await state.get_data()
        target_telegram_id = state_data.get("target_telegram_id")

    amount = plan['price']
    description = f"VPN Subscription ({plan['name']})"

    try:
        if method == "yookassa":
            url, payment_id = create_yookassa_payment(amount, description, f"user_{callback_query.from_user.id}_{plan_id}")
            db.create_pending_payment(payment_id, callback_query.from_user.id, plan['days'], target_telegram_id)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_yookassa_{payment_id}")]
            ])
            await callback_query.message.answer("Ссылка для оплаты сгенерирована:", reply_markup=kb)

        elif method == "cryptomus":
            url, payment_id = create_cryptomus_payment(amount, description, f"user_{callback_query.from_user.id}_{plan_id}")
            db.create_pending_payment(payment_id, callback_query.from_user.id, plan['days'], target_telegram_id)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_cryptomus_{payment_id}")]
            ])
            await callback_query.message.answer("Ссылка для оплаты сгенерирована:", reply_markup=kb)

    except Exception as e:
        logger.error(f"Payment generation error: {e}")
        await callback_query.message.answer("Произошла ошибка при генерации ссылки на оплату. Попробуйте позже.")

@dp.callback_query(F.data.startswith("check_"))
async def process_check_payment(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data = callback_query.data.split("_")
    method = data[1]
    payment_id = data[2]

    pending = db.get_pending_payment(payment_id)
    if not pending:
        await callback_query.message.answer("Платеж не найден или уже обработан.")
        return

    try:
        is_paid = False
        if method == "yookassa":
            is_paid = check_yookassa_payment(payment_id)
        elif method == "cryptomus":
            is_paid = check_cryptomus_payment(payment_id)

        if is_paid:
            target_id = pending['target_telegram_id'] if pending['target_telegram_id'] is not None else pending['telegram_id']
            await process_successful_subscription(callback_query.message, target_id, pending['plan_duration_days'])
            if pending['target_telegram_id'] is not None:
                try:
                    await bot.send_message(target_id, "Вам подарили подписку!")
                except Exception as e:
                    logger.error(f"Failed to notify gift recipient: {e}")
            db.delete_pending_payment(payment_id)
        else:
            await callback_query.message.answer("Оплата пока не поступила. Попробуйте проверить через минуту.")
    except Exception as e:
        logger.error(f"Payment check error: {e}")
        await callback_query.message.answer("Произошла ошибка при проверке оплаты.")

async def process_successful_subscription(message: types.Message, user_id: int, duration_days: int):
    user = db.get_user(user_id)
    now = datetime.datetime.now()

    if user:
        sub_id = user['sub_id']
        client_uuid = user['client_uuid']
        if not client_uuid:
            client_uuid = str(uuid.uuid4())
            conn = db.sqlite3.connect(db.DB_FILE)
            conn.cursor().execute("UPDATE users SET client_uuid = ? WHERE telegram_id = ?", (client_uuid, user_id))
            conn.commit()
            conn.close()

        if user['expires_at']:
            # Parse datetime string from DB
            current_expiry = datetime.datetime.fromisoformat(user['expires_at']) if isinstance(user['expires_at'], str) else user['expires_at']
            if current_expiry > now:
                new_expiry = current_expiry + datetime.timedelta(days=duration_days)
            else:
                new_expiry = now + datetime.timedelta(days=duration_days)
        else:
            new_expiry = now + datetime.timedelta(days=duration_days)

        db.update_user_expiry(user_id, new_expiry)
        logger.info(f"User {user_id} subscription extended to {new_expiry}.")

    else:
        sub_id = str(uuid.uuid4())
        client_uuid = str(uuid.uuid4())
        new_expiry = now + datetime.timedelta(days=duration_days)
        db.create_user(user_id, sub_id, client_uuid, new_expiry)
        logger.info(f"User {user_id} created with subscription until {new_expiry}.")

    # Configure panels
    email = f"tg_{user_id}_{sub_id[:8]}"
    expiry_time_ms = int(new_expiry.timestamp() * 1000)

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

    is_renewal = user is not None and user['client_uuid'] is not None

    if de_inbounds:
        inbound_id = de_inbounds[0]['id']
        if is_renewal:
            success = de_client.update_client(client_uuid, inbound_id, email, sub_id, expiry_time_ms)
            if not success:
                logger.info(f"Failed to update DE client {client_uuid}, attempting to re-add.")
                de_client.add_client(inbound_id, email, sub_id, client_uuid, expiry_time_ms)
        else:
            de_client.add_client(inbound_id, email, sub_id, client_uuid, expiry_time_ms)
    else:
        logger.error("No inbounds found on DE server")

    if nl_inbounds:
        inbound_id = nl_inbounds[0]['id']
        if is_renewal:
            success = nl_client.update_client(client_uuid, inbound_id, email, sub_id, expiry_time_ms)
            if not success:
                logger.info(f"Failed to update NL client {client_uuid}, attempting to re-add.")
                nl_client.add_client(inbound_id, email, sub_id, client_uuid, expiry_time_ms)
        else:
            nl_client.add_client(inbound_id, email, sub_id, client_uuid, expiry_time_ms)
    else:
        logger.error("No inbounds found on NL server")

    aggregator_url = os.environ.get("AGGREGATOR_URL", "http://localhost:8080").rstrip('/')
    final_link = f"{aggregator_url}/sub/{sub_id}"

    await message.answer(
        f"✅ Подписка успешно оформлена!\n\nВаша ссылка для подписки:\n`{final_link}`\n\n"
        "Скопируйте эту ссылку и вставьте в Hiddify. Серверы подтянутся автоматически.",
        parse_mode="Markdown"
    )

    if duration_days > 3:
        referrer_info = db.get_referrer(user_id)
        if referrer_info and not referrer_info['rewarded']:
            referrer_id = referrer_info['referrer_id']
            referrer_user = db.get_user(referrer_id)
            if referrer_user:
                current_expiry = datetime.datetime.fromisoformat(referrer_user['expires_at']) if isinstance(referrer_user['expires_at'], str) else referrer_user['expires_at']
                if current_expiry > now:
                    new_ref_expiry = current_expiry + datetime.timedelta(days=10)
                else:
                    new_ref_expiry = now + datetime.timedelta(days=10)

                db.update_user_expiry(referrer_id, new_ref_expiry)
                db.mark_referral_rewarded(user_id)

                ref_email = f"tg_{referrer_id}_{referrer_user['sub_id'][:8]}"
                ref_expiry_ms = int(new_ref_expiry.timestamp() * 1000)
                if de_inbounds:
                    de_client.update_client(referrer_user['client_uuid'], de_inbounds[0]['id'], ref_email, referrer_user['sub_id'], ref_expiry_ms)
                if nl_inbounds:
                    nl_client.update_client(referrer_user['client_uuid'], nl_inbounds[0]['id'], ref_email, referrer_user['sub_id'], ref_expiry_ms)

                try:
                    await bot.send_message(referrer_id, "Ваш друг приобрел подписку! Вам начислено 10 дней бесплатно.")
                except Exception as e:
                    logger.error(f"Failed to notify referrer: {e}")
