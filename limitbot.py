from storage import (
    get_user,
    save_user,
    get_stat,
    inc_stat,
    mark_daily_activity,
    get_dau
)

import asyncio
import logging
from datetime import date, timedelta
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    LabeledPrice
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# -----------------------------
# НАСТРОЙКИ
# -----------------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

ACCESS_DAYS = 30
PRICE_STARS = 300
MAX_SPENT = 1_000_000

# -----------------------------
# ЛОГИРОВАНИЕ
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------------
# КНОПКИ
# -----------------------------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Сегодня")],
        [KeyboardButton(text="Я потратил")],
        [KeyboardButton(text="Изменить сумму")]
    ],
    resize_keyboard=True
)

start_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Начать")]],
    resize_keyboard=True
)

pay_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⭐ Оплатить доступ")]],
    resize_keyboard=True
)

PAY_TEXT = (
    "🚫 Доступ закрыт.\n\n"
    "Оплати доступ, чтобы бот продолжил работу."
)

# -----------------------------
# FSM
# -----------------------------
class Setup(StatesGroup):
    monthly_amount = State()
    total_days = State()

class Spending(StatesGroup):
    today_spent = State()

# -----------------------------
# ДОСТУП
# -----------------------------
def has_access(user: dict, user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    return user.get("paid_until") and user["paid_until"] >= date.today()

# -----------------------------
# ЛОГИКА
# -----------------------------
def recalc(user_id: int):
    user = get_user(user_id)
    if not user:
        return

    today = date.today()
    if user["last_date"] == today:
        return

    days_passed = max(0, (today - user["last_date"]).days)

    for _ in range(days_passed):
        user["money_left"] -= user["today_spent"]
        user["days_left"] = max(1, user["days_left"] - 1)
        user["daily_limit"] = max(0, int(user["money_left"] / user["days_left"]))
        user["today_spent"] = 0

    user["last_date"] = today
    save_user(user_id, user)

# -----------------------------
# /start
# -----------------------------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    inc_stat("starts")
    mark_daily_activity(message.from_user.id)

    await state.clear()
    await message.answer(
        "Этот бот показывает,\n"
        "сколько денег можно потратить сегодня,\n"
        "чтобы не остаться без денег в конце месяца.",
        reply_markup=start_kb
    )

# -----------------------------
# НАЧАТЬ
# -----------------------------
@dp.message(F.text == "Начать")
async def begin(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user or not has_access(user, user_id):
        await message.answer(PAY_TEXT, reply_markup=pay_kb)
        return

    await state.set_state(Setup.monthly_amount)
    await message.answer("Сколько денег у тебя есть на месяц?")

# -----------------------------
# ВВОД СУММЫ
# -----------------------------
@dp.message(Setup.monthly_amount)
async def set_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число.")
        return

    await state.update_data(monthly_amount=int(message.text))
    await state.set_state(Setup.total_days)
    await message.answer("На сколько дней распределить сумму? (по умолчанию 30)")

# -----------------------------
# ВВОД ДНЕЙ
# -----------------------------
@dp.message(Setup.total_days)
async def set_days(message: Message, state: FSMContext):
    data = await state.get_data()
    total_days = int(message.text) if message.text.isdigit() and int(message.text) > 0 else 30

    daily_limit = max(0, int(data["monthly_amount"] / total_days))

    user = {
        "days_left": total_days,
        "money_left": data["monthly_amount"],
        "daily_limit": daily_limit,
        "today_spent": 0,
        "last_date": date.today(),
        "paid_until": date.today() + timedelta(days=ACCESS_DAYS)
    }

    save_user(message.from_user.id, user)
    await state.clear()

    await message.answer(f"Твой дневной лимит: {daily_limit} ₽", reply_markup=main_kb)

# -----------------------------
# СЕГОДНЯ
# -----------------------------
@dp.message(F.text == "Сегодня")
async def today(message: Message):
    user_id = message.from_user.id
    mark_daily_activity(user_id)

    user = get_user(user_id)
    if not user or not has_access(user, user_id):
        await message.answer(PAY_TEXT, reply_markup=pay_kb)
        return

    recalc(user_id)
    user = get_user(user_id)

    left = user["daily_limit"] - user["today_spent"]
    await message.answer(f"Сегодня:\nДневной лимит — {left} ₽")

# -----------------------------
# Я ПОТРАТИЛ
# -----------------------------
@dp.message(F.text == "Я потратил")
async def spent(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or not has_access(user, message.from_user.id):
        await message.answer(PAY_TEXT, reply_markup=pay_kb)
        return

    await state.set_state(Spending.today_spent)
    await message.answer("Сколько ты потратил сегодня?")

@dp.message(Spending.today_spent)
async def spent_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите число.")
        return

    spent = int(message.text)
    if spent <= 0 or spent > MAX_SPENT:
        await message.answer("Некорректная сумма.")
        return

    user = get_user(message.from_user.id)

    inc_stat("spent_actions")
    mark_daily_activity(message.from_user.id)

    user["today_spent"] += spent
    remaining = user["daily_limit"] - user["today_spent"]

    save_user(message.from_user.id, user)
    await state.clear()

    await message.answer(
        f"Осталось на сегодня: {remaining} ₽"
        if remaining >= 0
        else f"Ты вышел за лимит на {abs(remaining)} ₽"
    )

# -----------------------------
# ⭐ ОПЛАТА STARS
# -----------------------------
@dp.message(F.text == "⭐ Оплатить доступ")
async def pay_stars(message: Message):
    inc_stat("pay_clicks")

    await bot.send_invoice(
        chat_id=message.chat.id,
        title="MoneyLimit — доступ на 30 дней",
        description="Полный доступ к боту",
        payload="moneylimit_30",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=PRICE_STARS)]
    )

@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    try:
        user = get_user(message.from_user.id)
        if not user:
            user = {
                "days_left": 30,
                "money_left": 0,
                "daily_limit": 0,
                "today_spent": 0,
                "last_date": date.today(),
                "paid_until": None
            }

        base = user["paid_until"] if user.get("paid_until") and user["paid_until"] > date.today() else date.today()
        user["paid_until"] = base + timedelta(days=ACCESS_DAYS)

        save_user(message.from_user.id, user)
        inc_stat("payments")

        await message.answer("✅ Оплата успешна. Доступ продлён.")
    except Exception:
        logger.exception("Ошибка при обработке оплаты")

# -----------------------------
# 👑 GRANT
# -----------------------------
@dp.message(F.text.startswith("/grant"))
async def grant_access(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        _, user_id, days = message.text.split()
        user_id = int(user_id)
        days = int(days)
        assert days > 0
    except:
        await message.answer("Формат: /grant user_id days")
        return

    user = get_user(user_id)
    if not user:
        await message.answer("Пользователь не найден")
        return

    user["paid_until"] = date.today() + timedelta(days=days)
    save_user(user_id, user)

    await message.answer(f"✅ Доступ выдан на {days} дней")

# -----------------------------
# 📊 /stats
# -----------------------------
@dp.message(F.text == "/stats")
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        f"📊 Статистика:\n"
        f"▶️ Запусков: {get_stat('starts')}\n"
        f"👤 DAU сегодня: {get_dau()}"
    )

@dp.message(F.text == "/stats_payments")
async def stats_payments(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    pay_clicks = get_stat("pay_clicks")
    payments = get_stat("payments")

    await message.answer(
        f"💰 Оплаты:\n"
        f"💳 Нажали оплатить: {pay_clicks}\n"
        f"✅ Успешных оплат: {payments}\n"
        f"❌ Не оплатили: {pay_clicks - payments}"
    )

# -----------------------------
# ЗАПУСК
# -----------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
