from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: set[int]
    timezone: str = "Asia/Novosibirsk"
    daily_report_time: str = "23:59"
    google_sheet_id: str | None = None
    google_service_account_json: str | None = None
    seed_on_start: bool = True
    seed_path: Path = Path("data/seed_budget.json")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def normalize_database_url(url: str) -> str:
    # Railway usually provides postgresql://. SQLAlchemy asyncpg needs postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = "postgresql://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return {6902361169, 5242555673}
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk:
            ids.add(int(chunk))
    return ids


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    seed_path = Path(os.getenv("SEED_PATH", "data/seed_budget.json"))
    seed_on_start = os.getenv("SEED_ON_START", "true").lower() in {"1", "true", "yes", "y", "да"}

    return Settings(
        bot_token=bot_token,
        database_url=normalize_database_url(database_url),
        admin_ids=parse_admin_ids(os.getenv("ADMIN_IDS")),
        timezone=os.getenv("TIMEZONE", "Asia/Novosibirsk"),
        daily_report_time=os.getenv("DAILY_REPORT_TIME", "23:59"),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID") or None,
        google_service_account_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or None,
        seed_on_start=seed_on_start,
        seed_path=seed_path,
    )


def service_account_info(raw_json: str | None) -> dict | None:
    if not raw_json:
        return None
    raw_json = raw_json.strip()
    if raw_json.startswith("{"):
        return json.loads(raw_json)
    # Also allow path to mounted/secret file.
    p = Path(raw_json)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None
