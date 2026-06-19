from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, service_account_info
from app.models import Category, Transaction


RU_MONTHS = {
    1: ["январь", "января"],
    2: ["февраль", "февраля"],
    3: ["март", "марта"],
    4: ["апрель", "апреля"],
    5: ["май", "мая"],
    6: ["июнь", "июня"],
    7: ["июль", "июля"],
    # В текущей таблице месяц написан с опечаткой "Авуст" — учитываем оба варианта.
    8: ["август", "августа", "авуст"],
    9: ["сентябрь", "сентября"],
    10: ["октябрь", "октября"],
    11: ["ноябрь", "ноября"],
    12: ["декабрь", "декабря"],
}


def _to_float(x) -> float:
    if isinstance(x, Decimal):
        return float(x)
    return float(x or 0)


def _amount_text(amount: Decimal) -> str:
    s = format(Decimal(str(amount)).quantize(Decimal("0.01")), "f")
    if s.endswith(".00"):
        s = s[:-3]
    return s


def _strip_emoji_and_symbols(text: str) -> str:
    # Оставляем буквы/цифры/пробелы, чтобы категории сопоставлялись даже с emoji.
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    text = re.sub(r"[^a-zа-я0-9\s]+", " ", text)
    text = re.sub(r"\b(вместе|домой|соло|на|работе|и|для|по|пр)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _month_norm(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower().replace("ё", "е").strip())


def _cell_day(value: str) -> int | None:
    raw = str(value or "").strip().replace(",", ".")
    if re.fullmatch(r"\d{1,2}(?:\.0+)?", raw):
        day = int(float(raw))
        if 1 <= day <= 31:
            return day
    return None


def _parse_number(value: str) -> Decimal | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
        return Decimal(raw)
    return None


def _append_amount_to_cell(old_value: str | None, amount: Decimal) -> str:
    add = _amount_text(amount)
    old = str(old_value or "").strip()
    if not old:
        return add
    if old.startswith("="):
        return f"{old}+{add}"
    parsed = _parse_number(old)
    if parsed is not None:
        return f"={_amount_text(parsed)}+{add}"
    # Если в ячейке неожиданный текст, не ломаем её сложной формулой — записываем сумму.
    return add


def _best_row_by_category(values: list[list[str]], start_row: int, category_col: int, category: Category) -> int | None:
    target_variants = [category.name]
    target_variants.extend([x.strip() for x in (category.aliases or "").splitlines() if x.strip()])
    target_norms = [_strip_emoji_and_symbols(x) for x in target_variants if _strip_emoji_and_symbols(x)]
    if not target_norms:
        return None

    best_row: int | None = None
    best_score = 0.0

    for idx in range(start_row - 1, min(len(values), start_row + 80)):
        row = values[idx] if idx < len(values) else []
        if category_col - 1 >= len(row):
            continue
        raw_name = row[category_col - 1]
        if not raw_name:
            # После блока категорий идут пустые/итоговые строки.
            if idx > start_row:
                break
            continue
        row_norm = _strip_emoji_and_symbols(raw_name)
        if not row_norm or "итог" in row_norm or "всего" in row_norm:
            break

        for target in target_norms:
            if row_norm == target:
                return idx + 1
            if target in row_norm or row_norm in target:
                score = min(len(target), len(row_norm)) / max(len(target), len(row_norm))
            else:
                row_tokens = set(row_norm.split())
                target_tokens = set(target.split())
                if not row_tokens or not target_tokens:
                    score = 0.0
                else:
                    score = len(row_tokens & target_tokens) / len(target_tokens)
            if score > best_score:
                best_score = score
                best_row = idx + 1

    return best_row if best_score >= 0.55 else None


def _find_month_anchor(values: list[list[str]], month: date) -> tuple[int, int] | None:
    candidates = {_month_norm(x) for x in RU_MONTHS[month.month]}
    for r, row in enumerate(values, start=1):
        for c, value in enumerate(row, start=1):
            if _month_norm(str(value)) in candidates:
                return r, c
    return None


def _find_day_col(values: list[list[str]], day_header_row: int, day: int) -> int | None:
    if day_header_row < 1 or day_header_row > len(values):
        return None
    row = values[day_header_row - 1]
    for c, value in enumerate(row, start=1):
        if _cell_day(value) == day:
            return c
    return None


def _rowcol_to_a1(row: int, col: int) -> str:
    letters = ""
    n = col
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def _get_all_values_formula(ws) -> list[list[str]]:
    try:
        return ws.get_all_values(value_render_option="FORMULA")
    except TypeError:
        return ws.get_all_values()


def _get_cell_formula(ws, row: int, col: int) -> str:
    try:
        return ws.cell(row, col, value_render_option="FORMULA").value or ""
    except TypeError:
        return ws.cell(row, col).value or ""


def _update_cell_user_entered(ws, row: int, col: int, value: str) -> None:
    a1 = _rowcol_to_a1(row, col)
    ws.update([[value]], a1, value_input_option="USER_ENTERED")


def _income_category_candidates(tx: Transaction) -> list[str]:
    text = f"{tx.comment or ''}".lower().replace("ё", "е")

    # Доход с Telegram аккаунта: определяем владельца автоматически
    # Артём/Кирилл не должны попадать в "Разное"
    if "доп" in text or "подработ" in text or "фриланс" in text:
        return ["Доп. заработок", "Доп заработок"]

    if tx.person == "Кирилл":
        return ["ЗП Кирилл"]

    if tx.person == "Артём":
        return ["ЗП Артём", "ЗП Артем"]

    return ["Разное (родсвенники)", "Разное (родственники)", "Разное"]


def _find_income_row(values: list[list[str]], start_row: int, category_col: int, candidates: Iterable[str]) -> int | None:
    target_norms = [_strip_emoji_and_symbols(x) for x in candidates]
    for idx in range(start_row - 1, min(len(values), start_row + 20)):
        row = values[idx] if idx < len(values) else []
        raw_name = row[category_col - 1] if category_col - 1 < len(row) else ""
        row_norm = _strip_emoji_and_symbols(raw_name)
        if not row_norm:
            continue
        if "общий доход" in row_norm:
            break
        for target in target_norms:
            if row_norm == target or target in row_norm or row_norm in target:
                return idx + 1
    return None


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

    def _worksheet_existing(self, title: str):
        sh = self._open()
        if sh is None:
            return None
        return sh.worksheet(title)

    async def sync_all(self, session: AsyncSession, month: date) -> str:
        """Не создаём отдельные листы. Проверяем доступ к основным листам."""
        if not self.enabled:
            return "Google Sheets не подключён: нет GOOGLE_SHEET_ID или GOOGLE_SERVICE_ACCOUNT_JSON."
        self._worksheet_existing("Расходы")
        self._worksheet_existing("Доходы")
        return "Google Sheets доступен. Новые операции будут записываться в основные листы «Расходы» и «Доходы»."

    async def sync_transaction_to_main_sheet(self, tx: Transaction, category: Category | None = None) -> str:
        if not self.enabled:
            return "Google Sheets не подключён."
        if tx.tx_type == "expense":
            if category is None:
                return "Расход не записан в Google Sheets: не указана категория."
            return self._write_expense(tx, category)
        if tx.tx_type == "income":
            return self._write_income(tx)
        return "Тип операции не поддерживается."

    def _write_expense(self, tx: Transaction, category: Category) -> str:
        ws = self._worksheet_existing("Расходы")
        values = _get_all_values_formula(ws)
        anchor = _find_month_anchor(values, tx.tx_date)
        if not anchor:
            raise RuntimeError(f"Не нашёл месяц {RU_MONTHS[tx.tx_date.month][0].capitalize()} на листе «Расходы»")

        month_row, _ = anchor
        header_row = month_row + 2
        category_start_row = header_row + 1
        category_col = 1  # A
        day_col = _find_day_col(values, header_row, tx.tx_date.day)
        if not day_col:
            raise RuntimeError(f"Не нашёл число {tx.tx_date.day} в блоке месяца на листе «Расходы»")

        category_row = _best_row_by_category(values, category_start_row, category_col, category)
        if not category_row:
            raise RuntimeError(f"Не нашёл категорию «{category.name}» в блоке месяца на листе «Расходы»")
        
        old = _get_cell_formula(ws, category_row, day_col)
        amount = _amount_text(Decimal(str(tx.amount)))
        if tx.comment:
            new_value = f"{amount} ({tx.comment})"
        else:
            new_value = amount
        if old:
            new_value = f"{old}; {new_value}"
        _update_cell_user_entered(ws, category_row, day_col, new_value)
        return f"Записано в «Расходы»!{_rowcol_to_a1(category_row, day_col)}"

    def _write_income(self, tx: Transaction) -> str:
        ws = self._worksheet_existing("Доходы")
        values = _get_all_values_formula(ws)
        anchor = _find_month_anchor(values, tx.tx_date)
        if not anchor:
            raise RuntimeError(f"Не нашёл месяц {RU_MONTHS[tx.tx_date.month][0].capitalize()} на листе «Доходы»")

        month_row, _ = anchor
        day_header_row = month_row + 1
        category_start_row = month_row + 3
        category_col = 2  # B
        day_col = _find_day_col(values, day_header_row, tx.tx_date.day)
        if not day_col:
            raise RuntimeError(f"Не нашёл число {tx.tx_date.day} в блоке месяца на листе «Доходы»")

        row = _find_income_row(values, category_start_row, category_col, _income_category_candidates(tx))
        if not row:
            raise RuntimeError("Не нашёл подходящую строку дохода на листе «Доходы»")

        old = _get_cell_formula(ws, row, day_col)
        new_value = _append_amount_to_cell(old, Decimal(str(tx.amount)))
        _update_cell_user_entered(ws, row, day_col, new_value)
        return f"Записано в «Доходы»!{_rowcol_to_a1(row, day_col)}"

    # Старые методы оставлены пустыми, чтобы старые вызовы не создавали лишние листы.
    async def sync_categories(self, session: AsyncSession) -> None:
        return None

    async def sync_transactions(self, session: AsyncSession) -> None:
        return None

    async def sync_summary(self, session: AsyncSession, month: date) -> None:
        return None
