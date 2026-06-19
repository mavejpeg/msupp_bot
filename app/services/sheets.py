from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, service_account_info
from app.models import Category, Transaction
from app.services.budget import month_summary
from app.utils import money


def _to_float(x) -> float:
    if isinstance(x, Decimal):
        return float(x)
    return float(x or 0)


class SheetsSync:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = bool(settings.google_sheet_id and settings.google_service_account_json)
        self._client = None
        self._spreadsheet = None

    def _open(self):
        if not self.enabled:
            return None
        if self._spreadsheet is not None:
            return self._spreadsheet
        import gspread
        info = service_account_info(self.settings.google_service_account_json)
        if not info:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON or path")
        self._client = gspread.service_account_from_dict(info)
        self._spreadsheet = self._client.open_by_key(self.settings.google_sheet_id)
        return self._spreadsheet

    def _worksheet(self, title: str, rows: int = 1000, cols: int = 20):
        sh = self._open()
        if sh is None:
            return None
        try:
            return sh.worksheet(title)
        except Exception:
            return sh.add_worksheet(title=title, rows=rows, cols=cols)

    async def sync_all(self, session: AsyncSession, month: date) -> str:
        if not self.enabled:
            return "Google Sheets не подключён: нет GOOGLE_SHEET_ID или GOOGLE_SERVICE_ACCOUNT_JSON."
        await self.sync_categories(session)
        await self.sync_transactions(session)
        await self.sync_summary(session, month)
        return "Google Sheets обновлён."

    async def sync_categories(self, session: AsyncSession) -> None:
        ws = self._worksheet("Категории", rows=100, cols=8)
        if ws is None:
            return
        cats = list(await session.scalars(select(Category).order_by(Category.sort_order, Category.id)))
        values = [["Категория", "Группа", "Правило переноса", "% догоняния долга", "Алиасы"]]
        for c in cats:
            values.append([c.name, c.group, c.carry_rule, _to_float(c.debt_catchup_percent), c.aliases or ""])
        ws.clear()
        ws.update(values, value_input_option="USER_ENTERED")

    async def sync_transactions(self, session: AsyncSession) -> None:
        ws = self._worksheet("Операции", rows=2000, cols=8)
        if ws is None:
            return
        result = await session.scalars(
            select(Transaction).options(selectinload(Transaction.category)).order_by(Transaction.tx_date.desc(), Transaction.id.desc()).limit(1500)
        )
        values = [["Дата", "Тип", "Кто", "Категория", "Сумма", "Комментарий", "Создано"]]
        for tx in result:
            values.append([
                tx.tx_date.isoformat(),
                "Расход" if tx.tx_type == "expense" else "Доход",
                tx.person,
                tx.category.name if tx.category else "",
                _to_float(tx.amount),
                tx.comment or "",
                tx.created_at.isoformat() if tx.created_at else "",
            ])
        ws.clear()
        ws.update(values, value_input_option="USER_ENTERED")

    async def sync_summary(self, session: AsyncSession, month: date) -> None:
        ws = self._worksheet("Сводка", rows=200, cols=10)
        if ws is None:
            return
        s = await month_summary(session, month)
        values = [
            ["Месяц", s["month"].isoformat()],
            ["План дохода", _to_float(s["planned_income"])],
            ["Факт дохода", _to_float(s["income"])],
            ["План расходов", _to_float(s["planned_expense"])],
            ["Факт расходов", _to_float(s["expense"])],
            ["Остаток бюджета", _to_float(s["remaining_budget"])],
            [],
            ["Категория", "Группа", "План", "Факт", "Остаток", "Правило"],
        ]
        for line in s["lines"]:
            values.append([line["category"], line["group"], _to_float(line["planned"]), _to_float(line["spent"]), _to_float(line["remaining"]), line["carry_rule"]])
        ws.clear()
        ws.update(values, value_input_option="USER_ENTERED")
