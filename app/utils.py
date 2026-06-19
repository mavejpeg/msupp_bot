from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def money(value) -> str:
    d = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{d:,.2f}".replace(",", " ")
    if s.endswith(".00"):
        s = s[:-3]
    return f"{s} ₽"


def parse_amount(text: str) -> Decimal | None:
    m = re.search(r"(?<!\d)(\d+(?:[\s_]?\d{3})*(?:[,.]\d{1,2})?|\d+)(?!\d)", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace("_", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except Exception:
        return None


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def month_end(d: date) -> date:
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)


def next_month_start(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def days_left_in_month(today: date) -> int:
    return max(1, (month_end(today) - today).days + 1)


def now_date(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def parse_month_arg(text: str, default: date) -> date:
    # accepts YYYY-MM or MM.YYYY; returns first day
    parts = text.strip().split()
    for p in parts:
        if re.fullmatch(r"20\d{2}-\d{1,2}", p):
            y, m = map(int, p.split("-"))
            return date(y, m, 1)
        if re.fullmatch(r"\d{1,2}\.20\d{2}", p):
            m, y = map(int, p.split("."))
            return date(y, m, 1)
    return month_start(default)
