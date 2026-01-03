from storage import (
    get_user,
    save_user,
    get_stat,
    inc_stat,
    mark_daily_activity
)
from storage import get_dau

import asyncio
from datetime import date

import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

print(f"Token: {BOT_TOKEN[:10] if BOT_TOKEN else 'NOT LOADED'}...")


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# -----------------------------



# -----------------------------
# Кнопки
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

# -----------------------------
# FSM
# -----------------------------
class Setup(StatesGroup):
    monthly_amount = State()
    total_days = State()

class Spending(StatesGroup):
    today_spent = State()

# -----------------------------
# Вспомогательные функции
# -----------------------------
def recalc(user_id: int):
    user = get_user(user_id)
    if not user:
        return

    today = date.today()

    # если день не сменился — ничего не делаем
    if user["last_date"] == today:
        return

    # сколько дней прошло
    days_passed = (today - user["last_date"]).days

    for _ in range(days_passed):
        # закрываем каждый прошедший день
        user["money_left"] -= user["today_spent"]
        user["days_left"] = max(1, user["days_left"] - 1)

        # пересчитываем лимит
        user["daily_limit"] = int(user["money_left"] / user["days_left"])

        # сбрасываем траты дня
        user["today_spent"] = 0

    user["last_date"] = today

    save_user(user_id, user)

def get_today_text(user_id: int) -> str:
    user = get_user(user_id)
    return f"Сегодня:\nДневной лимит — {user['daily_limit']} ₽"

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
        "сколько денег тебе можно потратить сегодня,\n"
        "чтобы не остаться без денег в конце месяца.",
        reply_markup=start_kb
    )


# -----------------------------
# Начать
# -----------------------------
@dp.message(F.text == "Начать")
async def begin(message: Message, state: FSMContext):
    await state.set_state(Setup.monthly_amount)
    await message.answer("Сколько денег у тебя есть на месяц?")

# -----------------------------
# Ввод суммы
# -----------------------------
@dp.message(Setup.monthly_amount)
async def set_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return

    await state.update_data(monthly_amount=int(message.text))
    await state.set_state(Setup.total_days)
    await message.answer(
        "На сколько дней ты хочешь распределить эту сумму?\n"
        "(по умолчанию: 30)"
    )

# -----------------------------
# Ввод дней
# -----------------------------
@dp.message(Setup.total_days)
async def set_days(message: Message, state: FSMContext):
    data = await state.get_data()
    total_days = int(message.text) if message.text.isdigit() else 30

    daily_limit = int(data["monthly_amount"] / total_days)

    user = {
    "days_left": total_days,
    "money_left": data["monthly_amount"],
    "daily_limit": daily_limit,
    "today_spent": 0,
    "last_date": date.today()
}
    save_user(message.from_user.id, user)

    await state.clear()

    await message.answer(
        f"Твой дневной лимит: {daily_limit} ₽\n\n"
        f"Сегодня ты можешь потратить\n"
        f"до {daily_limit} ₽\n"
        f"и остаться в рамках месяца.",
        reply_markup=main_kb
    )

# -----------------------------
# Сегодня
# -----------------------------
@dp.message(F.text == "Сегодня")
async def today(message: Message):
    mark_daily_activity(message.from_user.id)
    user_id = message.from_user.id
    
    user = get_user(user_id)
    if not user:
        return

    recalc(user_id)

    user = get_user(user_id)

    left = user["daily_limit"] - user["today_spent"]

    await message.answer(
        f"Сегодня:\n"
        f"Дневной лимит — {left} ₽"
    )
# -----------------------------
# Я потратил
# -----------------------------
@dp.message(F.text == "Я потратил")
async def spent(message: Message, state: FSMContext):
    await state.set_state(Spending.today_spent)
    await message.answer("Сколько ты потратил сегодня?")

@dp.message(Spending.today_spent)
async def spent_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return

    user = get_user(message.from_user.id)
    if not user:
        return

    spent = int(message.text)
    if spent <= 0:
        return
    
    inc_stat("spent_actions")
    mark_daily_activity(message.from_user.id)

     # фиксируем трату СЕГОДНЯ
    user["today_spent"] += spent

    remaining = user["daily_limit"] - user["today_spent"]

    if remaining >= 0:
        text = f"Осталось на сегодня: {remaining} ₽"
    else:
        text = (
            f"Ты вышел за лимит на {abs(remaining)} ₽\n"
            f"Завтра лимит будет меньше."
        )

    save_user(message.from_user.id, user)

    await state.clear()
    await message.answer(text)

# -----------------------------
# Изменить сумму
# -----------------------------
@dp.message(F.text == "Изменить сумму")
async def reset(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Setup.monthly_amount)
    await message.answer("Сколько денег у тебя есть на месяц?")


@dp.message(F.text == "/stats")
async def stats_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    starts = get_stat("starts")
    spent = get_stat("spent_actions")

    dau = get_dau()

    await message.answer(
        f"📊 Статистика:\n"
        f"▶️ Запусков: {starts}\n"
        f"💸 Трат: {spent}\n"
        f"👤 DAU сегодня: {dau}"
    )
# -------- ---------------------
# Запуск
# -----------------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
