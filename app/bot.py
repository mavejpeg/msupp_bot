from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from decimal import Decimal

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import FSInputFile, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings, load_settings
from app.db import SessionLocal, close_engine, create_schema, init_engine
from app.keyboards import categories_keyboard, main_keyboard
from app.models import Category
from app.services.budget import (
    add_transaction,
    create_or_recalculate_plan,
    find_category,
    list_categories,
    month_summary,
    seed_database,
    today_total,
)
from app.services.export import export_xlsx
from app.services.sheets import SheetsSync
from app.utils import days_left_in_month, money, month_start, now_date, parse_amount, parse_month_arg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
router = Router()


class AddExpense(StatesGroup):
    category = State()
    amount = State()


class AddIncome(StatesGroup):
    amount = State()


def is_allowed(message: Message, settings: Settings) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_ids)


async def guard(message: Message) -> bool:
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    if not is_allowed(message, settings):
        await message.answer("⛔️ Нет доступа к семейному бюджету.")
        return False
    return True


def person_from_user(user_id: int | None) -> str:
    if user_id == 6902361169:
        return "Артём"
    if user_id == 5242555673:
        return "Кирилл"
    return "Общее"


def override_person(text: str, default: str) -> str:
    t = text.lower()
    if "кирилл" in t or "кир " in t:
        return "Кирилл"
    if "артём" in t or "артем" in t or "арт " in t:
        return "Артём"
    if "общее" in t or "вместе" in t:
        return "Общее"
    return default


def short_label(idx: int, cat: Category) -> str:
    name = cat.name
    # Remove some long descriptors for Telegram buttons.
    cleaned = re.sub(r"\([^)]*\)", "", name).strip()
    cleaned = cleaned.replace("/рестораны/фастфуд/столовка/обеды", "/фастфуд")
    if len(cleaned) > 48:
        cleaned = cleaned[:45].rstrip() + "…"
    return f"{idx}. {cleaned}"


async def categories_labels(session) -> tuple[list[str], dict[str, int]]:
    cats = await list_categories(session)
    labels = []
    mapping = {}
    for i, cat in enumerate(cats, start=1):
        label = short_label(i, cat)
        labels.append(label)
        mapping[str(i)] = cat.id
        mapping[label] = cat.id
    return labels, mapping


async def category_from_label(session, text: str) -> Category | None:
    cats = await list_categories(session)
    m = re.match(r"^(\d{1,2})[.)\s]", text.strip())
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= len(cats):
            return cats[idx - 1]
    return await find_category(session, text)


async def render_summary(session, month, title: str = "📊 Сводка") -> str:
    s = await month_summary(session, month)
    planned = s["planned_expense"]
    spent = s["expense"]
    remaining = s["remaining_budget"]
    income = s["income"]
    planned_income = s["planned_income"]
    m = s["month"]
    # daily limit for current month only is calculated outside if needed.
    lines = [
        f"<b>{title} за {m.strftime('%m.%Y')}</b>",
        "",
        f"План дохода: <b>{money(planned_income)}</b>",
        f"Факт дохода: <b>{money(income)}</b>",
        f"План расходов: <b>{money(planned)}</b>",
        f"Факт расходов: <b>{money(spent)}</b>",
        f"Остаток бюджета: <b>{money(remaining)}</b>",
        f"Свободные деньги по факту: <b>{money(s['free_money'])}</b>",
    ]
    # Biggest spent categories.
    top = sorted([x for x in s["lines"] if x["spent"] > 0], key=lambda x: x["spent"], reverse=True)[:5]
    if top:
        lines.append("\n<b>Топ расходов:</b>")
        for item in top:
            lines.append(f"• {item['category']}: {money(item['spent'])}")
    return "\n".join(lines)


async def render_limits(session, month) -> str:
    s = await month_summary(session, month)
    lines = [f"<b>📉 Лимиты за {s['month'].strftime('%m.%Y')}</b>", ""]
    for item in s["lines"]:
        planned = item["planned"]
        spent = item["spent"]
        rem = item["remaining"]
        if rem < 0:
            mark = "🔴"
        elif planned > 0 and rem <= planned / 2:
            mark = "🟡"
        else:
            mark = "🟢"
        lines.append(f"{mark} {item['category']}\n   план {money(planned)} / факт {money(spent)} / ост. {money(rem)}")
    return "\n".join(lines)


async def render_plan(session, month) -> str:
    s = await month_summary(session, month)
    lines = [f"<b>🧾 План на {s['month'].strftime('%m.%Y')}</b>", "", f"Всего расходов: <b>{money(s['planned_expense'])}</b>"]
    grouped: dict[str, list] = {}
    for item in s["lines"]:
        grouped.setdefault(item["group"], []).append(item)
    for group, items in grouped.items():
        lines.append(f"\n<b>{group}</b>")
        for item in items:
            lines.append(f"• {item['category']}: {money(item['planned'])}")
    return "\n".join(lines)


@router.message(Command("start"))
async def start(message: Message):
    if not await guard(message):
        return
    await message.answer(
        "Готов. Я буду считать семейный бюджет, принимать расходы/доходы и синхронизировать Google Sheets.\n\n"
        "Быстрый ввод: <code>продукты 950 магнит</code> или <code>доход 5000 подработка</code>.",
        reply_markup=main_keyboard(),
    )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь")
async def help_cmd(message: Message):
    if not await guard(message):
        return
    await message.answer(
        "<b>Команды</b>\n"
        "/summary — сводка месяца\n"
        "/limits — остатки по категориям\n"
        "/plan — план месяца\n"
        "/plan 2026-07 — план конкретного месяца\n"
        "/sync — обновить Google Sheets\n"
        "/export — получить Excel-отчёт\n\n"
        "<b>Быстрый расход</b>\n"
        "<code>продукты 950 магнит</code>\n"
        "<code>такси артём 430</code>\n\n"
        "<b>Быстрый доход</b>\n"
        "<code>доход 5000 подработка</code>\n"
        "<code>зп кирилл 12000</code>",
        reply_markup=main_keyboard(),
    )


@router.message(Command("summary"))
@router.message(F.text == "📊 Сводка")
async def summary_cmd(message: Message):
    if not await guard(message):
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        today = now_date(settings.tz)
        s = await month_summary(session, today)
        txt = await render_summary(session, today)
        daily_limit = s["remaining_budget"] / Decimal(days_left_in_month(today))
        txt += f"\n\nМожно тратить в день: <b>{money(daily_limit)}</b>"
        await message.answer(txt, reply_markup=main_keyboard())


@router.message(Command("limits"))
@router.message(F.text == "📉 Лимиты")
async def limits_cmd(message: Message):
    if not await guard(message):
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        await message.answer(await render_limits(session, now_date(settings.tz)), reply_markup=main_keyboard())


@router.message(Command("plan"))
@router.message(F.text == "🧾 План")
async def plan_cmd(message: Message):
    if not await guard(message):
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    month = parse_month_arg(message.text or "", now_date(settings.tz))
    async with SessionLocal() as session:  # type: ignore[misc]
        await create_or_recalculate_plan(session, month)
        await message.answer(await render_plan(session, month), reply_markup=main_keyboard())


@router.message(Command("sync"))
@router.message(F.text == "🔄 Sync Sheets")
async def sync_cmd(message: Message):
    if not await guard(message):
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    sheets: SheetsSync = message.bot.sheets  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        try:
            msg = await sheets.sync_all(session, now_date(settings.tz))
        except Exception as e:
            log.exception("Google Sheets sync failed")
            msg = f"Ошибка синхронизации: {e}"
    await message.answer(msg, reply_markup=main_keyboard())


@router.message(Command("export"))
@router.message(F.text == "📤 Excel")
async def export_cmd(message: Message):
    if not await guard(message):
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        path = await export_xlsx(session, now_date(settings.tz))
    await message.answer_document(FSInputFile(path, filename="family_budget_report.xlsx"), caption="Готово: Excel-отчёт")


@router.message(F.text == "➕ Расход")
@router.message(Command("add_expense"))
async def add_expense_start(message: Message, state: FSMContext):
    if not await guard(message):
        return
    async with SessionLocal() as session:  # type: ignore[misc]
        labels, _ = await categories_labels(session)
    await state.set_state(AddExpense.category)
    await message.answer("Выбери категорию расхода:", reply_markup=categories_keyboard(labels))


@router.message(AddExpense.category)
async def add_expense_category(message: Message, state: FSMContext):
    if not await guard(message):
        return
    if message.text == "⬅️ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=main_keyboard())
        return
    async with SessionLocal() as session:  # type: ignore[misc]
        cat = await category_from_label(session, message.text or "")
    if not cat:
        await message.answer("Не понял категорию. Выбери кнопку или напиши номер категории.")
        return
    await state.update_data(category_id=cat.id, category_name=cat.name)
    await state.set_state(AddExpense.amount)
    await message.answer(f"Категория: <b>{cat.name}</b>\nТеперь введи сумму и комментарий, например: <code>950 магнит</code>")


@router.message(AddExpense.amount)
async def add_expense_amount(message: Message, state: FSMContext):
    if not await guard(message):
        return
    if message.text == "⬅️ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=main_keyboard())
        return
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer("Не вижу сумму. Напиши, например: <code>950 магнит</code>")
        return
    data = await state.get_data()
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    sheets: SheetsSync = message.bot.sheets  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        cat = await session.get(Category, data["category_id"])
        person = person_from_user(message.from_user.id if message.from_user else None)
        person = override_person(message.text or "", person)
        comment = re.sub(r"(?<!\d)\d+(?:[\s_]?\d{3})*(?:[,.]\d{1,2})?(?!\d)", "", message.text or "").strip()
        await add_transaction(session, "expense", amount, now_date(settings.tz), person, cat, comment, message.from_user.id if message.from_user else None)
        try:
            await sheets.sync_all(session, now_date(settings.tz))
        except Exception:
            log.exception("Sheets sync after expense failed")
    await state.clear()
    await message.answer(f"✅ Расход добавлен: {money(amount)}\n{cat.name if cat else ''}", reply_markup=main_keyboard())


@router.message(F.text == "➕ Доход")
@router.message(Command("add_income"))
async def add_income_start(message: Message, state: FSMContext):
    if not await guard(message):
        return
    await state.set_state(AddIncome.amount)
    await message.answer("Введи сумму дохода и комментарий, например: <code>5000 подработка</code>")


@router.message(AddIncome.amount)
async def add_income_amount(message: Message, state: FSMContext):
    if not await guard(message):
        return
    if message.text == "⬅️ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=main_keyboard())
        return
    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer("Не вижу сумму. Напиши, например: <code>5000 подработка</code>")
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    sheets: SheetsSync = message.bot.sheets  # type: ignore[attr-defined]
    person = person_from_user(message.from_user.id if message.from_user else None)
    person = override_person(message.text or "", person)
    comment = re.sub(r"(?<!\d)\d+(?:[\s_]?\d{3})*(?:[,.]\d{1,2})?(?!\d)", "", message.text or "").strip()
    async with SessionLocal() as session:  # type: ignore[misc]
        await add_transaction(session, "income", amount, now_date(settings.tz), person, None, comment, message.from_user.id if message.from_user else None)
        try:
            await sheets.sync_all(session, now_date(settings.tz))
        except Exception:
            log.exception("Sheets sync after income failed")
    await state.clear()
    await message.answer(f"✅ Доход добавлен: {money(amount)}", reply_markup=main_keyboard())


@router.message(F.text)
async def quick_input(message: Message):
    if not await guard(message):
        return
    text = message.text or ""
    amount = parse_amount(text)
    if amount is None:
        await message.answer("Не понял. Пример: <code>продукты 950 магнит</code>", reply_markup=main_keyboard())
        return
    settings: Settings = message.bot.settings  # type: ignore[attr-defined]
    sheets: SheetsSync = message.bot.sheets  # type: ignore[attr-defined]
    is_income = text.lower().strip().startswith(("доход", "зп", "зарплата", "+доход"))
    person = override_person(text, person_from_user(message.from_user.id if message.from_user else None))
    comment = re.sub(r"(?<!\d)\d+(?:[\s_]?\d{3})*(?:[,.]\d{1,2})?(?!\d)", "", text).strip()
    async with SessionLocal() as session:  # type: ignore[misc]
        cat = None
        if not is_income:
            cat = await find_category(session, text)
            if not cat:
                await message.answer("Не нашёл категорию. Лучше нажми «➕ Расход» и выбери из списка.", reply_markup=main_keyboard())
                return
        await add_transaction(session, "income" if is_income else "expense", amount, now_date(settings.tz), person, cat, comment, message.from_user.id if message.from_user else None)
        try:
            await sheets.sync_all(session, now_date(settings.tz))
        except Exception:
            log.exception("Sheets sync after quick input failed")
    await message.answer(
        f"✅ {'Доход' if is_income else 'Расход'} добавлен: {money(amount)}" + (f"\n{cat.name}" if cat else ""),
        reply_markup=main_keyboard(),
    )


async def daily_report(bot: Bot):
    settings: Settings = bot.settings  # type: ignore[attr-defined]
    sheets: SheetsSync = bot.sheets  # type: ignore[attr-defined]
    async with SessionLocal() as session:  # type: ignore[misc]
        today = now_date(settings.tz)
        s = await month_summary(session, today)
        spent_today = await today_total(session, today, "expense")
        limit = s["remaining_budget"] / Decimal(days_left_in_month(today))
        text = (
            "<b>🌙 Ежедневная сводка</b>\n\n"
            f"Сегодня потрачено: <b>{money(spent_today)}</b>\n"
            f"Остаток бюджета месяца: <b>{money(s['remaining_budget'])}</b>\n"
            f"Можно тратить в день: <b>{money(limit)}</b>"
        )
        try:
            await sheets.sync_all(session, today)
        except Exception:
            log.exception("Daily sheets sync failed")
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            log.exception("Failed to send daily report to %s", admin_id)


async def main():
    settings = load_settings()
    init_engine(settings.database_url)
    await create_schema()
    async with SessionLocal() as session:  # type: ignore[misc]
        if settings.seed_on_start:
            await seed_database(session, settings.seed_path)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot.settings = settings  # type: ignore[attr-defined]
    bot.sheets = SheetsSync(settings)  # type: ignore[attr-defined]

    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=settings.tz)
    hh, mm = [int(x) for x in settings.daily_report_time.split(":")]
    scheduler.add_job(daily_report, CronTrigger(hour=hh, minute=mm, timezone=settings.tz), args=[bot], id="daily_report", replace_existing=True)
    scheduler.start()

    log.info("Bot started. Allowed users: %s", sorted(settings.admin_ids))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await close_engine()


if __name__ == "__main__":
    asyncio.run(main())
