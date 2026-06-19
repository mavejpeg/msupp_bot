from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Расход"), KeyboardButton(text="➕ Доход")],
            [KeyboardButton(text="📊 Сводка"), KeyboardButton(text="📉 Лимиты")],
            [KeyboardButton(text="🧾 План"), KeyboardButton(text="🔄 Sync Sheets")],
            [KeyboardButton(text="📤 Excel"), KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Например: продукты 950 магнит",
    )


def categories_keyboard(names: list[str]) -> ReplyKeyboardMarkup:
    rows = []
    for i in range(0, len(names), 2):
        rows.append([KeyboardButton(text=n) for n in names[i:i+2]])
    rows.append([KeyboardButton(text="⬅️ Отмена")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def persons_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Артём"), KeyboardButton(text="Кирилл"), KeyboardButton(text="Общее")],
            [KeyboardButton(text="⬅️ Отмена")],
        ],
        resize_keyboard=True,
    )
