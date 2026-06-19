from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BudgetLine, Category, MonthlyPlan, Transaction, User
from app.utils import month_end, month_start, next_month_start


DEFAULT_GUARANTEED_INCOME = Decimal("172471.65")
DEFAULT_RESERVE_PERCENT = Decimal("0.10")


def dec(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def seed_database(session: AsyncSession, seed_path: Path) -> None:
    if not seed_path.exists():
        return
    existing = await session.scalar(select(func.count(Category.id)))
    data = json.loads(seed_path.read_text(encoding="utf-8"))

    # Users are upserted on every start.
    for u in data.get("users", []):
        user = await session.scalar(select(User).where(User.telegram_id == int(u["telegram_id"])))
        if user is None:
            session.add(User(telegram_id=int(u["telegram_id"]), name=u.get("name") or str(u["telegram_id"])))

    if existing and existing > 0:
        await session.commit()
        return

    category_by_key: dict[str, Category] = {}
    for order, c in enumerate(data.get("categories", []), start=1):
        cat = Category(
            key=c["key"],
            name=c["name"],
            group=c.get("group", "Жизнь"),
            carry_rule=c.get("carry_rule", "normal_reduce_by_overspend"),
            debt_catchup_percent=dec(c.get("debt_catchup_percent", 0)),
            aliases="\n".join(c.get("aliases", [])),
            sort_order=order,
        )
        session.add(cat)
        category_by_key[c["key"]] = cat
    await session.flush()

    settings = data.get("settings", {})
    guaranteed = dec(settings.get("default_guaranteed_income", DEFAULT_GUARANTEED_INCOME))
    reserve = dec(settings.get("reserve_percent", DEFAULT_RESERVE_PERCENT))

    for month_str, mdata in data.get("monthly", {}).items():
        year, month = map(int, month_str.split("-"))
        m_start = date(year, month, 1)
        plan = MonthlyPlan(
            month=m_start,
            planned_income=dec(mdata.get("planned_income", guaranteed)),
            guaranteed_income=guaranteed,
            reserve_percent=reserve,
            comment="Импорт из Excel",
        )
        session.add(plan)
        await session.flush()
        for cdata in data.get("categories", []):
            cat = category_by_key[cdata["key"]]
            session.add(BudgetLine(
                plan_id=plan.id,
                category_id=cat.id,
                rule_value=dec(cdata.get("rules", {}).get(month_str, 0)),
                planned_amount=dec(cdata.get("plans", {}).get(month_str, 0)),
                source="excel_import",
            ))

    # Import detailed transactions from Excel only once.
    for tx in data.get("transactions", []):
        tx_date = date.fromisoformat(tx["date"])
        cat = category_by_key.get(tx.get("category_key")) if tx.get("category_key") else None
        session.add(Transaction(
            tx_date=tx_date,
            tx_type=tx["type"],
            person=tx.get("person") or "Общее",
            category_id=cat.id if cat else None,
            amount=dec(tx["amount"]),
            comment=tx.get("comment") or "Импорт из Excel",
        ))
    await session.commit()


async def list_categories(session: AsyncSession) -> list[Category]:
    result = await session.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.id))
    return list(result)


async def find_category(session: AsyncSession, text: str) -> Category | None:
    text_l = text.lower().strip()
    cats = await list_categories(session)
    # First exact alias/name matches.
    for cat in cats:
        if text_l == cat.name.lower():
            return cat
        aliases = [a.strip().lower() for a in (cat.aliases or "").splitlines() if a.strip()]
        if text_l in aliases:
            return cat
    # Then fuzzy contains.
    for cat in cats:
        target = cat.name.lower()
        aliases = [a.strip().lower() for a in (cat.aliases or "").splitlines() if a.strip()]
        if any(a in text_l for a in aliases) or any(word and word in target for word in text_l.split()):
            return cat
    return None


async def add_transaction(
    session: AsyncSession,
    tx_type: str,
    amount: Decimal,
    tx_date: date,
    person: str = "Общее",
    category: Category | None = None,
    comment: str = "",
    created_by: int | None = None,
) -> Transaction:
    tx = Transaction(
        tx_date=tx_date,
        tx_type=tx_type,
        person=person,
        amount=amount,
        category_id=category.id if category else None,
        comment=comment,
        created_by=created_by,
    )
    session.add(tx)
    await session.commit()
    await session.refresh(tx)
    return tx


async def get_month_plan(session: AsyncSession, month: date) -> MonthlyPlan | None:
    m = month_start(month)
    return await session.scalar(
        select(MonthlyPlan).options(selectinload(MonthlyPlan.lines).selectinload(BudgetLine.category)).where(MonthlyPlan.month == m)
    )


async def expense_by_category(session: AsyncSession, month: date) -> dict[int, Decimal]:
    m1 = month_start(month)
    m2 = next_month_start(m1)
    rows = await session.execute(
        select(Transaction.category_id, func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.tx_type == "expense", Transaction.tx_date >= m1, Transaction.tx_date < m2, Transaction.category_id.is_not(None))
        .group_by(Transaction.category_id)
    )
    return {int(cid): dec(total) for cid, total in rows if cid is not None}


async def total_for_month(session: AsyncSession, month: date, tx_type: str) -> Decimal:
    m1 = month_start(month)
    m2 = next_month_start(m1)
    total = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.tx_type == tx_type,
            Transaction.tx_date >= m1,
            Transaction.tx_date < m2,
        )
    )
    return dec(total)


async def today_total(session: AsyncSession, today: date, tx_type: str = "expense") -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.tx_type == tx_type, Transaction.tx_date == today)
    )
    return dec(total)


def calculate_base(rule_value: Decimal, guaranteed_income: Decimal) -> Decimal:
    rule_value = dec(rule_value)
    if Decimal("0") < rule_value < Decimal("1"):
        return guaranteed_income * rule_value
    return rule_value


async def create_or_recalculate_plan(session: AsyncSession, month: date, guaranteed_income: Decimal | None = None) -> MonthlyPlan:
    m = month_start(month)
    existing = await get_month_plan(session, m)
    if existing is not None:
        return existing

    prev_month_end = m.replace(day=1)
    # Date of previous month first day.
    if m.month == 1:
        prev = date(m.year - 1, 12, 1)
    else:
        prev = date(m.year, m.month - 1, 1)

    prev_plan = await get_month_plan(session, prev)
    prev_fact = await expense_by_category(session, prev)
    cats = await list_categories(session)
    guaranteed = dec(guaranteed_income or DEFAULT_GUARANTEED_INCOME)

    plan = MonthlyPlan(month=m, planned_income=guaranteed, guaranteed_income=guaranteed, reserve_percent=DEFAULT_RESERVE_PERCENT, comment="Автоплан")
    session.add(plan)
    await session.flush()

    prev_line_by_cat = {}
    if prev_plan:
        prev_line_by_cat = {line.category_id: line for line in prev_plan.lines}

    for cat in cats:
        prev_line = prev_line_by_cat.get(cat.id)
        rule_value = prev_line.rule_value if prev_line else Decimal("0")
        base = calculate_base(rule_value, guaranteed)
        prev_planned = dec(prev_line.planned_amount) if prev_line else Decimal("0")
        prev_spent = dec(prev_fact.get(cat.id, 0))
        prev_remaining = prev_planned - prev_spent

        amount = base
        if cat.carry_rule == "mandatory_full_carry":
            amount = base + prev_remaining
        elif cat.carry_rule == "debt_partial_carry":
            cap = base * dec(cat.debt_catchup_percent or 0)
            amount = base + min(prev_remaining, cap)
        elif cat.carry_rule == "normal_reduce_by_overspend":
            amount = base + min(Decimal("0"), prev_remaining)
        elif cat.carry_rule == "strict_zero_if_overspend":
            amount = Decimal("0") if prev_remaining < 0 else base
        elif cat.carry_rule == "fixed_no_carry":
            amount = base

        if amount < 0:
            amount = Decimal("0")
        session.add(BudgetLine(plan_id=plan.id, category_id=cat.id, rule_value=rule_value, planned_amount=amount, source="auto"))

    await session.commit()
    return await get_month_plan(session, m)  # type: ignore[return-value]


async def month_summary(session: AsyncSession, month: date) -> dict:
    plan = await create_or_recalculate_plan(session, month)
    spent_by_cat = await expense_by_category(session, month)
    income = await total_for_month(session, month, "income")
    expense = await total_for_month(session, month, "expense")
    planned_expense = sum(dec(line.planned_amount) for line in plan.lines)
    lines = []
    for line in sorted(plan.lines, key=lambda l: (l.category.sort_order, l.category.id)):
        spent = dec(spent_by_cat.get(line.category_id, 0))
        planned = dec(line.planned_amount)
        lines.append({
            "category_id": line.category_id,
            "category": line.category.name,
            "group": line.category.group,
            "planned": planned,
            "spent": spent,
            "remaining": planned - spent,
            "carry_rule": line.category.carry_rule,
        })
    return {
        "month": month_start(month),
        "planned_income": dec(plan.planned_income),
        "guaranteed_income": dec(plan.guaranteed_income),
        "income": income,
        "planned_expense": planned_expense,
        "expense": expense,
        "remaining_budget": planned_expense - expense,
        "free_money": income - expense,
        "lines": lines,
    }
