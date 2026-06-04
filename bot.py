import os
import uuid
import datetime
import logging
import asyncio
from aiogram import Bot, Dispatcher, F, types, BaseMiddleware
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

import db
from xui_api import XUIClient
from payments import create_yookassa_payment, check_yookassa_payment, create_cryptocloud_payment, check_cryptocloud_payment
from aiogram.types import LabeledPrice, PreCheckoutQuery
import uuid

class GiftSub(StatesGroup):
    waiting_for_username = State()

class SupportStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()

class CheckoutStates(StatesGroup):
    checkout = State()
    waiting_for_promocode = State()


logger = logging.getLogger(__name__)

bot = Bot(token=os.environ.get("BOT_TOKEN", "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"))
dp = Dispatcher()

class BlockMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = None
        if isinstance(event, types.Message):
            user_id = event.from_user.id
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id

        if user_id:
            user = db.get_user(user_id)
            if user and user['is_blocked'] == 1:
                if isinstance(event, types.CallbackQuery):
                    await event.answer("Вы заблокированы.", show_alert=True)
                return
        return await handler(event, data)

dp.message.middleware(BlockMiddleware())
dp.callback_query.middleware(BlockMiddleware())


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

    reply_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Меню")]],
        resize_keyboard=True,
        is_persistent=True
    )

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡 Купить подписку", callback_data="buy_sub")],
        [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="❤️ Пригласить друзей", callback_data="invite_friends")],
        [InlineKeyboardButton(text="🎁 Подарить подписку", callback_data="gift_sub")],
        [InlineKeyboardButton(text="🆘 Помощь / Поддержка", callback_data="help_btn")]
    ])

    await message.answer(
        "Добро пожаловать! Выберите действие:",
        reply_markup=reply_kb
    )
    await message.answer(
        "Главное меню:",
        reply_markup=inline_kb
    )

@dp.message(F.text == "Меню")
async def process_menu_text(message: types.Message, state: FSMContext):
    await state.clear()

    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡 Купить подписку", callback_data="buy_sub")],
        [InlineKeyboardButton(text="👤 Мой аккаунт", callback_data="my_account")],
        [InlineKeyboardButton(text="❤️ Пригласить друзей", callback_data="invite_friends")],
        [InlineKeyboardButton(text="🎁 Подарить подписку", callback_data="gift_sub")],
        [InlineKeyboardButton(text="🆘 Помощь / Поддержка", callback_data="help_btn")]
    ])

    await message.answer(
        "Главное меню:",
        reply_markup=inline_kb
    )

@dp.callback_query(F.data == "buy_sub")
async def process_buy_sub(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    buttons = []
    plans = db.get_all_plans()
    for plan_id, plan in plans.items():
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
        "За каждого приглашённого друга, который купит подписку, вы получите 50 рублей на баланс!",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "my_account")
async def process_my_account(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    user = db.get_user(callback_query.from_user.id)

    if not user:
        await callback_query.message.answer("Информация о вашем аккаунте не найдена.")
        return

    now = datetime.datetime.now()
    expires_at = user['expires_at']
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.datetime.fromisoformat(expires_at)
        except ValueError:
            # Fallback if needed, though db should contain valid iso format
            expires_at = None

    if expires_at and expires_at > now:
        status = "✅ Активна"
        expiry_str = expires_at.strftime("%d.%m.%Y %H:%M")
    else:
        status = "❌ Неактивна"
        expiry_str = expires_at.strftime("%d.%m.%Y %H:%M") if expires_at else "Нет данных"

    balance = user['balance'] if 'balance' in user.keys() else 0.0

    text = (
        f"👤 **Ваш аккаунт**\n\n"
        f"Статус подписки: {status}\n"
        f"Действует до: {expiry_str}\n"
        f"💵 Баланс: {balance:.2f} руб."
    )

    await callback_query.message.answer(text, parse_mode="Markdown")

@dp.callback_query(F.data == "help_btn")
async def process_help_btn(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    await _send_help(callback_query.message)

@dp.message(Command("help"))
async def process_help_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await _send_help(message)

async def _send_help(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать в поддержку", callback_data="support_contact")]
    ])
    await message.answer(
        "🆘 **Помощь и инструкции**\n\n"
        "1. Скачайте приложение Hiddify (доступно в App Store и Google Play).\n"
        "2. Скопируйте ссылку, которую вам выдал бот после оплаты.\n"
        "3. Откройте Hiddify, нажмите '+' и выберите 'Добавить из буфера обмена'.\n"
        "4. Нажмите кнопку 'Подключить'.\n\n"
        "Если у вас возникли проблемы, нажмите кнопку ниже, чтобы написать в поддержку.",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.callback_query(F.data == "support_contact")
async def process_support_contact(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.set_state(SupportStates.waiting_for_message)
    await callback_query.message.answer("Опишите вашу проблему, и мы постараемся помочь вам как можно скорее:")

@dp.message(SupportStates.waiting_for_message)
async def process_support_message(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if admin_id_str.isdigit():
        admin_id = int(admin_id_str)
        username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ответить", callback_data=f"support_reply_{message.from_user.id}")]
        ])

        await bot.send_message(
            admin_id,
            f"🆘 **Новое обращение в поддержку:**\n\nОт: {username} (`{message.from_user.id}`)\n\n{message.text}",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await message.answer("Ваше сообщение отправлено в поддержку. Ожидайте ответа.")
    else:
        await message.answer("Ошибка: администратор не настроен.")

    await state.clear()

@dp.callback_query(F.data.startswith("support_reply_"))
async def process_support_reply_btn(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    target_id = callback_query.data.split("_")[2]
    await state.set_state(SupportStates.waiting_for_reply)
    await state.update_data(support_target_id=target_id)
    await callback_query.message.answer(f"Введите ответ для пользователя `{target_id}`:", parse_mode="Markdown")

@dp.message(SupportStates.waiting_for_reply)
async def process_support_reply_message(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    data = await state.get_data()
    target_id = data.get("support_target_id")

    if target_id:
        try:
            await bot.send_message(
                target_id,
                f"🧑‍💻 **Ответ от поддержки:**\n\n{message.text}",
                parse_mode="Markdown"
            )
            await message.answer("Ответ успешно отправлен пользователю.")
        except Exception as e:
            logger.error(f"Failed to send support reply: {e}")
            await message.answer("Ошибка при отправке ответа.")

    await state.clear()

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
    plans = db.get_all_plans()
    for plan_id, plan in plans.items():
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
    plan = db.get_plan(plan_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить ⭐️ Telegram Stars", callback_data=f"giftpay_stars_{plan_id}")],
        [InlineKeyboardButton(text="Оплатить криптой (CryptoCloud)", callback_data=f"giftpay_cryptocloud_{plan_id}")],
        [InlineKeyboardButton(text="Оплатить картой (ЮКасса)", callback_data=f"giftpay_yookassa_{plan_id}")]
    ])
    await callback_query.message.answer(
        f"Вы выбрали тариф в подарок: {plan['name']}. Сумма к оплате: {plan['price']} руб.\nВыберите способ оплаты:",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("plan_"))
async def process_plan_selection(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    plan_id = callback_query.data.split("_")[1]
    plan = db.get_plan(plan_id)
    user_id = callback_query.from_user.id

    if plan_id == "trial":
        user = db.get_user(user_id)
        if user and user['trial_used']:
            await callback_query.message.answer("Вы уже использовали пробный период.")
            return

        await process_successful_subscription(callback_query.message, user_id, plan['days'])
        db.set_trial_used(user_id)
        return

    await state.set_state(CheckoutStates.checkout)
    await state.update_data(plan_id=plan_id, promo_code=None, use_balance=False)
    await render_checkout(callback_query.message, state, user_id)

async def render_checkout(message_or_callback: types.Message | types.CallbackQuery, state: FSMContext, user_id: int):
    data = await state.get_data()
    plan_id = data.get("plan_id")
    promo_code_str = data.get("promo_code")
    use_balance = data.get("use_balance", False)

    plan = db.get_plan(plan_id)
    user = db.get_user(user_id)

    base_price = plan['price']
    discount = 0.0

    if promo_code_str:
        promo = db.get_promocode(promo_code_str)
        if promo and promo['uses_left'] > 0 and (not promo['expires_at'] or datetime.datetime.fromisoformat(promo['expires_at']) > datetime.datetime.now()):
            if promo['discount_type'] == 'percent':
                discount = base_price * (promo['discount_value'] / 100.0)
            elif promo['discount_type'] == 'rub':
                discount = promo['discount_value']

    price_after_promo = max(0.0, base_price - discount)

    balance_used = 0.0
    if use_balance and user and 'balance' in user.keys() and user['balance'] > 0:
        balance_used = min(price_after_promo, user['balance'])

    final_price = max(0.0, price_after_promo - balance_used)

    await state.update_data(final_price=final_price, balance_used=balance_used, discount=discount)

    text = f"Вы выбрали тариф: {plan['name']}\n"
    text += f"Базовая цена: {base_price:.2f} руб.\n"

    if discount > 0:
        text += f"Скидка по промокоду: -{discount:.2f} руб.\n"
    if balance_used > 0:
        text += f"Использовано с баланса: -{balance_used:.2f} руб.\n"

    text += f"\n**Итого к оплате: {final_price:.2f} руб.**\n"

    buttons = []

    if not promo_code_str:
        buttons.append([InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="checkout_promocode")])
    if user and 'balance' in user.keys() and user['balance'] > 0 and not use_balance:
        buttons.append([InlineKeyboardButton(text=f"💵 Использовать баланс ({user['balance']:.2f} руб.)", callback_data="checkout_use_balance")])

    if final_price > 0:
        buttons.append([InlineKeyboardButton(text="Оплатить ⭐️ Telegram Stars", callback_data=f"pay_stars_{plan_id}")],
        [InlineKeyboardButton(text="Оплатить криптой (CryptoCloud)", callback_data=f"pay_cryptocloud_{plan_id}")])
        buttons.append([InlineKeyboardButton(text="Оплатить картой (ЮКасса)", callback_data=f"pay_yookassa_{plan_id}")])
    else:
        buttons.append([InlineKeyboardButton(text="✅ Оплатить балансом", callback_data=f"pay_balance_{plan_id}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "checkout_promocode")
async def process_checkout_promocode_btn(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.set_state(CheckoutStates.waiting_for_promocode)
    await callback_query.message.answer("Введите промокод:")

@dp.message(CheckoutStates.waiting_for_promocode)
async def process_checkout_promocode_input(message: types.Message, state: FSMContext):
    code = message.text.strip()
    promo = db.get_promocode(code)

    if not promo:
        await message.answer("Промокод не найден.")
    elif promo['uses_left'] <= 0:
        await message.answer("У этого промокода закончились использования.")
    elif promo['expires_at'] and datetime.datetime.fromisoformat(promo['expires_at']) <= datetime.datetime.now():
         await message.answer("Срок действия промокода истёк.")
    else:
        await message.answer(f"Промокод '{code}' успешно применён!")
        await state.update_data(promo_code=code)

    await state.set_state(CheckoutStates.checkout)
    await render_checkout(message, state, message.from_user.id)

@dp.callback_query(F.data == "checkout_use_balance")
async def process_checkout_use_balance(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.update_data(use_balance=True)
    await render_checkout(callback_query, state, callback_query.from_user.id)

@dp.callback_query(F.data.startswith("pay_") | F.data.startswith("giftpay_"))
async def process_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = callback_query.data.split("_")

    is_gift = data[0] == "giftpay"
    method = data[1]
    plan_id = data[2]
    plan = db.get_plan(plan_id)

    target_telegram_id = None
    state_data = await state.get_data()
    if is_gift:
        target_telegram_id = state_data.get("target_telegram_id")

    amount = state_data.get("final_price", plan['price'])
    balance_used = state_data.get("balance_used", 0.0)
    promo_code = state_data.get("promo_code")

    description = f"VPN Subscription ({plan['name']})"

    if method == "balance":
        if amount == 0:
            if balance_used > 0:
                db.update_balance(callback_query.from_user.id, -balance_used)
            if promo_code:
                db.use_promocode(promo_code)

            actual_amount_paid = plan['price'] - balance_used - state_data.get("discount", 0.0)
            db.record_sale(callback_query.from_user.id, plan_id, actual_amount_paid)

            await process_successful_subscription(callback_query.message, callback_query.from_user.id, plan['days'])
            await state.clear()
        return

    try:
        if method == "yookassa":
            url, payment_id = create_yookassa_payment(amount, description, f"user_{callback_query.from_user.id}_{plan_id}")
            db.create_pending_payment(payment_id, callback_query.from_user.id, plan['days'], target_telegram_id, plan_id, amount, promo_code, balance_used)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_yookassa_{payment_id}")]
            ])
            await callback_query.message.answer("Ссылка для оплаты сгенерирована:", reply_markup=kb)

        elif method == "cryptocloud":
            url, payment_id = create_cryptocloud_payment(amount, description, f"user_{callback_query.from_user.id}_{plan_id}")
            db.create_pending_payment(payment_id, callback_query.from_user.id, plan['days'], target_telegram_id, plan_id, amount, promo_code, balance_used)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_cryptocloud_{payment_id}")]
            ])
            await callback_query.message.answer("Ссылка для оплаты сгенерирована:", reply_markup=kb)

        elif method == "stars":
            payment_id = str(uuid.uuid4())
            stars_amount = int(amount)
            db.create_pending_payment(payment_id, callback_query.from_user.id, plan['days'], target_telegram_id, plan_id, amount, promo_code, balance_used)
            prices = [LabeledPrice(label=plan['name'], amount=stars_amount)]
            await bot.send_invoice(
                chat_id=callback_query.message.chat.id,
                title=f"Подписка {plan['name']}",
                description=description,
                payload=f"stars_{payment_id}",
                provider_token="",
                currency="XTR",
                prices=prices
            )

    except Exception as e:
        logger.error(f"Payment generation error: {e}")
        await callback_query.message.answer("Произошла ошибка при генерации ссылки на оплату. Попробуйте позже.")


@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("stars_"):
        payment_id = payload.split("stars_")[1]
        pending = db.get_pending_payment(payment_id)
        if not pending:
            return

        target_id = pending['target_telegram_id'] if pending['target_telegram_id'] is not None else pending['telegram_id']

        balance_used = pending['balance_used'] if 'balance_used' in pending.keys() else 0.0
        if balance_used > 0:
            db.update_balance(pending['telegram_id'], -balance_used)

        promo_code = pending['promo_code'] if 'promo_code' in pending.keys() else None
        if promo_code:
            db.use_promocode(promo_code)

        amount = pending['amount'] if 'amount' in pending.keys() else 0.0
        plan_id = pending['plan_id'] if 'plan_id' in pending.keys() else None

        if plan_id:
            db.record_sale(pending['telegram_id'], plan_id, amount)
        else:
            plans = db.get_all_plans()
            for p_id, plan_data in plans.items():
                if plan_data['days'] == pending['plan_duration_days']:
                    db.record_sale(pending['telegram_id'], p_id, plan_data['price'])
                    break

        await process_successful_subscription(message, target_id, pending['plan_duration_days'])

        if pending['target_telegram_id'] is not None:
            try:
                await bot.send_message(target_id, "Вам подарили подписку!")
            except Exception as e:
                import logging
                logging.error(f"Failed to notify gift recipient: {e}")
        db.delete_pending_payment(payment_id)

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
        elif method == "cryptocloud":
            is_paid = check_cryptocloud_payment(payment_id)

        if is_paid:
            target_id = pending['target_telegram_id'] if pending['target_telegram_id'] is not None else pending['telegram_id']

            balance_used = pending['balance_used'] if 'balance_used' in pending.keys() else 0.0
            if balance_used > 0:
                db.update_balance(pending['telegram_id'], -balance_used)

            promo_code = pending['promo_code'] if 'promo_code' in pending.keys() else None
            if promo_code:
                db.use_promocode(promo_code)

            amount = pending['amount'] if 'amount' in pending.keys() else 0.0
            plan_id = pending['plan_id'] if 'plan_id' in pending.keys() else None

            if plan_id:
                db.record_sale(pending['telegram_id'], plan_id, amount)
            else:
                plans = db.get_all_plans()
                for p_id, plan_data in plans.items():
                    if plan_data['days'] == pending['plan_duration_days']:
                        db.record_sale(pending['telegram_id'], p_id, plan_data['price'])
                        break

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
                db.update_balance(referrer_id, 50.0)
                db.mark_referral_rewarded(user_id)

                try:
                    await bot.send_message(referrer_id, "Ваш друг приобрел подписку! Вам начислено 50 рублей на баланс.")
                except Exception as e:
                    logger.error(f"Failed to notify referrer: {e}")

class AdminStates(StatesGroup):
    waiting_for_user_query = State()
    waiting_for_broadcast_msg = State()
    waiting_for_plan_price = State()
    waiting_for_promocode_code = State()
    waiting_for_promocode_discount_type = State()
    waiting_for_promocode_discount_value = State()
    waiting_for_promocode_uses = State()
    waiting_for_promocode_expires = State()

async def send_admin_panel(message: types.Message):
    stats = db.get_stats()
    plans = db.get_all_plans()

    top_plans_str = ""
    for idx, (plan_id, count) in enumerate(stats['top_plans']):
        plan_name = plans.get(plan_id, {}).get("name", plan_id)
        top_plans_str += f"{idx+1}. {plan_name} — {count} продаж\n"

    if not top_plans_str:
        top_plans_str = "Нет данных"

    graph_data = db.get_sales_graph_data()
    graph_str = "📈 **График продаж (7 дней):**\n"

    max_val = max([d['total'] for d in graph_data] + [1])

    for d in reversed(graph_data):
        date_str = d['date'].strftime("%d.%m")
        total = d['total']

        bars_count = int((total / max_val) * 10)
        bars = "▓" * bars_count + "░" * (10 - bars_count)

        graph_str += f"`{date_str}` | {bars} `{total:.0f}₽`\n"

    text = (
        f"🛠 **Админ-панель**\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"✅ Активных подписок: {stats['active_subs']}\n"
        f"❌ Истекших подписок: {stats['expired_subs']}\n"
        f"🆓 Пробных периодов: {stats['trial_users']}\n\n"
        f"💰 **Продажи**\n"
        f"Сегодня: {stats['sales_today']} шт. ({stats['earnings_today']:.0f} руб)\n"
        f"Неделя: {stats['sales_week']} шт. ({stats['earnings_week']:.0f} руб)\n"
        f"Месяц: {stats['sales_month']} шт. ({stats['earnings_month']:.0f} руб)\n\n"
        f"{graph_str}\n"
        f"🏆 **Топ тарифов:**\n{top_plans_str}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_search_user")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Тарифы", callback_data="admin_plans")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promocodes")]
    ])

    if isinstance(message, types.Message):
        await message.answer(text, reply_markup=kb)
    else:
        await message.message.edit_text(text, reply_markup=kb)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return
    await state.clear()
    await send_admin_panel(message)


@dp.callback_query(F.data == "admin_users_list")
async def admin_process_users_list(callback_query: types.CallbackQuery):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    users = db.get_all_users()

    file_content = "ID | Telegram ID | Username | Sub ID | Created | Expires | Blocked\n"
    file_content += "-" * 80 + "\n"

    for u in users:
        blocked = "Yes" if u['is_blocked'] else "No"
        username = f"@{u['username']}" if u['username'] else "None"
        sub_id = u['sub_id'][:8] + "..." if u['sub_id'] else "None"
        file_content += f"{u['id']} | {u['telegram_id']} | {username} | {sub_id} | {u['created_at']} | {u['expires_at']} | {blocked}\n"

    from aiogram.types import BufferedInputFile
    file = BufferedInputFile(file_content.encode("utf-8"), filename="users.txt")
    await callback_query.message.answer_document(document=file)


@dp.callback_query(F.data == "admin_search_user")
async def admin_process_search_user(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    await state.set_state(AdminStates.waiting_for_user_query)
    await callback_query.message.answer("Введите telegram_id или username пользователя (например, @username или 123456789):")

@dp.message(AdminStates.waiting_for_user_query)
async def admin_search_user_result(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    query = message.text.strip()
    user = db.search_user(query)

    if not user:
        await message.answer("Пользователь не найден.")
    else:
        status = "Заблокирован" if user['is_blocked'] else "Активен"
        username = f"@{user['username']}" if user['username'] else "Нет"

        text = (
            f"👤 **Пользователь найден:**\n\n"
            f"Telegram ID: `{user['telegram_id']}`\n"
            f"Username: {username}\n"
            f"Статус подписки (до): {user['expires_at'] or 'Нет данных'}\n"
            f"Статус: **{status}**"
        )

        buttons = []
        if user['is_blocked']:
            buttons.append([InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin_unblock_{user['telegram_id']}")])
        else:
            buttons.append([InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin_block_{user['telegram_id']}")])

        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)

    await state.clear()

@dp.callback_query(F.data.startswith("admin_block_") | F.data.startswith("admin_unblock_"))
async def admin_process_block_unblock(callback_query: types.CallbackQuery):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    data = callback_query.data.split("_")
    action = data[1]
    target_id = int(data[2])

    if action == "block":
        db.set_user_blocked(target_id, 1)
        await callback_query.message.answer(f"Пользователь {target_id} заблокирован.")
    elif action == "unblock":
        db.set_user_blocked(target_id, 0)
        await callback_query.message.answer(f"Пользователь {target_id} разблокирован.")


@dp.callback_query(F.data == "admin_broadcast")
async def admin_process_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback_query.message.answer("Отправьте сообщение для рассылки всем пользователям:")


@dp.message(AdminStates.waiting_for_broadcast_msg)
async def admin_do_broadcast(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    users = db.get_all_users()
    success_count = 0
    fail_count = 0

    await message.answer("Рассылка начата...")

    for u in users:
        if u['is_blocked']:
            continue
        try:
            await message.send_copy(chat_id=u['telegram_id'])
            success_count += 1
            await asyncio.sleep(0.05) # Rate limiting protection
        except Exception as e:
            logger.error(f"Failed to send broadcast to {u['telegram_id']}: {e}")
            fail_count += 1

    await message.answer(f"Рассылка завершена!\nУспешно: {success_count}\nОшибок: {fail_count}")
    await state.clear()

@dp.callback_query(F.data == "admin_plans")
async def process_admin_plans(callback_query: types.CallbackQuery):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    plans = db.get_all_plans()

    text = "⚙️ **Управление тарифами**\n\nВыберите тариф для изменения цены:"
    buttons = []
    for plan_id, plan in plans.items():
        buttons.append([InlineKeyboardButton(text=f"{plan['name']} - {plan['price']} руб.", callback_data=f"admin_edit_plan_{plan_id}")])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("admin_edit_plan_"))
async def process_admin_edit_plan(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    plan_id = callback_query.data.split("_")[3]
    plan = db.get_plan(plan_id)

    if not plan:
        await callback_query.message.answer("Тариф не найден.")
        return

    await state.set_state(AdminStates.waiting_for_plan_price)
    await state.update_data(edit_plan_id=plan_id)
    await callback_query.message.answer(f"Текущая цена для {plan['name']}: {plan['price']} руб.\nВведите новую цену в рублях (число):")

@dp.message(AdminStates.waiting_for_plan_price)
async def process_admin_set_plan_price(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    try:
        new_price = float(message.text.strip())
        if new_price < 0:
            raise ValueError("Price cannot be negative")

        data = await state.get_data()
        plan_id = data.get("edit_plan_id")

        db.update_plan_price(plan_id, new_price)
        await message.answer("✅ Цена тарифа успешно обновлена!")
        await send_admin_panel(message)
    except ValueError:
        await message.answer("❌ Ошибка: Введите корректное число (например, 150 или 150.50).")
        return

    await state.clear()

@dp.callback_query(F.data == "admin_promocodes")
async def process_admin_promocodes(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promocode")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ])
    await callback_query.message.edit_text("🎟 **Управление промокодами**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "admin_create_promocode")
async def process_admin_create_promocode(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    await state.set_state(AdminStates.waiting_for_promocode_code)
    await callback_query.message.answer("Введите код промокода (например, SALE50):")

@dp.message(AdminStates.waiting_for_promocode_code)
async def process_admin_promocode_code(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    code = message.text.strip()
    await state.update_data(promo_code=code)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Процент (%)", callback_data="promo_type_percent")],
        [InlineKeyboardButton(text="Рубли (руб)", callback_data="promo_type_rub")]
    ])
    await state.set_state(AdminStates.waiting_for_promocode_discount_type)
    await message.answer("Выберите тип скидки:", reply_markup=kb)

@dp.callback_query(AdminStates.waiting_for_promocode_discount_type)
async def process_admin_promocode_type(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    promo_type = callback_query.data.split("_")[2]
    await state.update_data(promo_type=promo_type)

    await state.set_state(AdminStates.waiting_for_promocode_discount_value)
    type_str = "%" if promo_type == "percent" else "руб."
    await callback_query.message.answer(f"Введите размер скидки в {type_str}:")

@dp.message(AdminStates.waiting_for_promocode_discount_value)
async def process_admin_promocode_value(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    try:
        value = float(message.text.strip())
        if value < 0:
            raise ValueError()
        await state.update_data(promo_value=value)

        await state.set_state(AdminStates.waiting_for_promocode_uses)
        await message.answer("Введите количество использований (число):")
    except ValueError:
        await message.answer("❌ Ошибка: Введите корректное число.")

@dp.message(AdminStates.waiting_for_promocode_uses)
async def process_admin_promocode_uses(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    try:
        uses = int(message.text.strip())
        if uses <= 0:
            raise ValueError()
        await state.update_data(promo_uses=uses)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Без ограничений по времени", callback_data="promo_expires_none")]
        ])
        await state.set_state(AdminStates.waiting_for_promocode_expires)
        await message.answer("Введите срок действия промокода в формате `ДД.ММ.ГГГГ` (например, 31.12.2024), либо выберите 'Без ограничений':", reply_markup=kb, parse_mode="Markdown")
    except ValueError:
        await message.answer("❌ Ошибка: Введите корректное целое число > 0.")

@dp.callback_query(AdminStates.waiting_for_promocode_expires, F.data == "promo_expires_none")
async def process_admin_promocode_expires_none(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    data = await state.get_data()
    success = db.create_promocode(data['promo_code'], data['promo_type'], data['promo_value'], data['promo_uses'], None)

    if success:
        await callback_query.message.answer(f"✅ Промокод `{data['promo_code']}` успешно создан!", parse_mode="Markdown")
    else:
        await callback_query.message.answer(f"❌ Ошибка: Промокод с таким кодом уже существует.")

    await state.clear()
    await send_admin_panel(callback_query.message)

@dp.message(AdminStates.waiting_for_promocode_expires)
async def process_admin_promocode_expires_date(message: types.Message, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or message.from_user.id != int(admin_id_str):
        return

    try:
        expires_date = datetime.datetime.strptime(message.text.strip(), "%d.%m.%Y")
        # Set to end of day
        expires_date = expires_date.replace(hour=23, minute=59, second=59)

        data = await state.get_data()
        success = db.create_promocode(data['promo_code'], data['promo_type'], data['promo_value'], data['promo_uses'], expires_date.isoformat())

        if success:
            await message.answer(f"✅ Промокод `{data['promo_code']}` успешно создан (действует до {message.text.strip()})!", parse_mode="Markdown")
        else:
            await message.answer(f"❌ Ошибка: Промокод с таким кодом уже существует.")

        await state.clear()
        await send_admin_panel(message)
    except ValueError:
        await message.answer("❌ Ошибка: Неверный формат даты. Введите в формате `ДД.ММ.ГГГГ`.")

@dp.callback_query(F.data == "admin_back")
async def process_admin_back(callback_query: types.CallbackQuery, state: FSMContext):
    admin_id_str = os.environ.get("ADMIN_ID", "")
    if not admin_id_str.isdigit() or callback_query.from_user.id != int(admin_id_str):
        await callback_query.answer()
        return

    await callback_query.answer()
    await state.clear()
    await send_admin_panel(callback_query)
