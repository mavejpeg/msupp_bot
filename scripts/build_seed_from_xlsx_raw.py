from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from zipfile import ZipFile

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
ns = {'m': NS}

SHEET_INDEX = {
    'Настройки': 1,
    'Доходы': 2,
    'Расходы': 3,
    'Сводка год': 4,
}

MONTHS = {
    'june': {'name': 'Июнь', 'month': '2026-06', 'settings_plan_col': 'V', 'settings_rule_col': 'U', 'expense_start': 4, 'expense_end': 26, 'expense_days_row': 3, 'expense_total_row': 28, 'income_start': 20, 'income_end': 24, 'income_days_row': 18},
    'july': {'name': 'Июль', 'month': '2026-07', 'settings_plan_col': 'X', 'settings_rule_col': 'W', 'expense_start': 37, 'expense_end': 59, 'expense_days_row': 36, 'expense_total_row': 61, 'income_start': 31, 'income_end': 35, 'income_days_row': 29},
    'august': {'name': 'Август', 'month': '2026-08', 'settings_plan_col': 'Z', 'settings_rule_col': 'Y', 'expense_start': 70, 'expense_end': 92, 'expense_days_row': 69, 'expense_total_row': 94, 'income_start': 41, 'income_end': 45, 'income_days_row': 39},
}

DAY_COLS = ['F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z','AA','AB','AC','AD','AE','AF','AG','AH','AI','AJ']
INCOME_DAY_COLS = ['H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z','AA','AB','AC','AD','AE','AF','AG','AH','AI','AJ','AK','AL']


def load_sst(z: ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in z.namelist():
        return []
    root = ET.fromstring(z.read('xl/sharedStrings.xml'))
    out = []
    for si in root.findall('m:si', ns):
        out.append(''.join(t.text or '' for t in si.findall('.//m:t', ns)))
    return out


def sheet_cells(z: ZipFile, sheet_idx: int) -> dict[str, dict]:
    ss = load_sst(z)
    root = ET.fromstring(z.read(f'xl/worksheets/sheet{sheet_idx}.xml'))
    cells: dict[str, dict] = {}
    for c in root.findall('.//m:c', ns):
        ref = c.attrib.get('r')
        t = c.attrib.get('t')
        v = c.find('m:v', ns)
        f = c.find('m:f', ns)
        val = None
        if v is not None:
            raw = v.text
            if t == 's':
                val = ss[int(raw)]
            elif t == 'b':
                val = bool(int(raw))
            else:
                try:
                    val = float(raw)
                except Exception:
                    val = raw
        isel = c.find('m:is', ns)
        if isel is not None:
            val = ''.join(tt.text or '' for tt in isel.findall('.//m:t', ns))
        if val is not None or f is not None:
            cells[ref] = {'v': val, 'f': f.text if f is not None else None}
    return cells


def val(cells: dict[str, dict], ref: str, default=None):
    item = cells.get(ref)
    if not item:
        return default
    return item.get('v', default)


def number(x, default=0.0) -> float:
    if x is None or x == '':
        return default
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x).replace(' ', '').replace(',', '.'))
    except Exception:
        return default


def slugify(name: str) -> str:
    cleaned = re.sub(r'[^a-zA-Zа-яА-Я0-9]+', '_', name.lower()).strip('_')
    return cleaned[:80] or 'category'


def group_for(name: str) -> str:
    n = name.lower()
    if 'долг' in n or 'коммунал' in n:
        return 'Долги и обязательные'
    if any(x in n for x in ['продукт', 'покушать', 'транспорт', 'такси', 'связь', 'гигиена', 'бытовые', 'котики']):
        return 'Жизнь'
    return 'Хотелки'


def carry_rule_for(name: str) -> str:
    n = name.lower()
    if 'коммунал' in n:
        return 'mandatory_full_carry'
    if 'погашение долга' in n:
        return 'debt_partial_carry'
    if 'развлеч' in n or 'кафе' in n or 'онлайн шопинг' in n or 'одежда' in n or 'подарки' in n:
        return 'strict_zero_if_overspend'
    if 'мобильная связь' in n or 'котики' in n or 'вредные' in n:
        return 'fixed_no_carry'
    return 'normal_reduce_by_overspend'


def aliases_for(name: str) -> list[str]:
    n = name.lower()
    aliases: list[str] = []
    if 'коммунал' in n: aliases += ['коммуналка', 'квартплата', 'жкх']
    if 'кирилл' in n and 'долг' in n: aliases += ['долг кирилл', 'кир долг']
    if 'арт' in n and 'долг' in n: aliases += ['долг артем', 'долг артём', 'арт долг']
    if 'продукт' in n: aliases += ['еда домой', 'продукты', 'магнит', 'пятерочка', 'пятёрочка', 'мария ра']
    if 'кафе' in n: aliases += ['кафе', 'фастфуд', 'ресторан', 'обеды вместе']
    if 'кирилл' in n and 'покушать' in n: aliases += ['еда кирилл', 'кир еда', 'кирилл покушать']
    if 'артём' in n and 'покушать' in n or 'артем' in n and 'покушать' in n: aliases += ['еда артем', 'еда артём', 'арт еда', 'артём покушать']
    if 'самокаты арт' in n: aliases += ['самокат артем', 'самокаты артем', 'самокат артём']
    if 'самокаты кир' in n: aliases += ['самокат кирилл', 'самокаты кирилл']
    if 'транспорт' in n: aliases += ['транспорт', 'автобус', 'метро', 'электричка']
    if 'таксии вместе' in n or 'такси вместе' in n: aliases += ['такси вместе', 'такси общее']
    if 'такси кирилл' in n: aliases += ['такси кирилл', 'кир такси']
    if 'такси арт' in n: aliases += ['такси артем', 'такси артём', 'арт такси']
    if 'мобильная' in n: aliases += ['связь', 'интернет', 'подписки', 'впн']
    if 'развлеч' in n: aliases += ['развлечения', 'отдых', 'клуб', 'аттракционы', 'атракционы']
    if 'вредные' in n: aliases += ['вейп', 'алко', 'вредные']
    if 'одежда' in n: aliases += ['одежда', 'шмот']
    if 'гигиена' in n: aliases += ['гигиена', 'здоровье', 'лекарства', 'косметика']
    if 'бытовые' in n: aliases += ['быт', 'химия', 'бытовые']
    if 'котики' in n: aliases += ['котики', 'кот', 'кошки']
    if 'онлайн' in n: aliases += ['онлайн', 'шопинг', 'маркетплейс', 'wb', 'wildberries', 'озон', 'ozon']
    if 'подарки' in n: aliases += ['подарки', 'близкие']
    if 'другое' in n: aliases += ['другое', 'прочее']
    return sorted(set(aliases))


def build_seed(xlsx_path: Path) -> dict:
    with ZipFile(xlsx_path) as z:
        settings = sheet_cells(z, SHEET_INDEX['Настройки'])
        expenses = sheet_cells(z, SHEET_INDEX['Расходы'])
        incomes = sheet_cells(z, SHEET_INDEX['Доходы'])

    categories = []
    for row in range(10, 34):
        name = val(settings, f'R{row}')
        if not name:
            continue
        cat = {
            'key': slugify(name),
            'name': str(name).strip(),
            'group': group_for(str(name)),
            'carry_rule': carry_rule_for(str(name)),
            'debt_catchup_percent': 0.20 if carry_rule_for(str(name)) == 'debt_partial_carry' else 0.0,
            'aliases': aliases_for(str(name)),
            'settings_row': row,
            'rules': {
                '2026-06': number(val(settings, f'U{row}')),
                '2026-07': number(val(settings, f'W{row}')),
                '2026-08': number(val(settings, f'Y{row}')),
            },
            'plans': {
                '2026-06': number(val(settings, f'V{row}')),
                '2026-07': number(val(settings, f'X{row}')),
                '2026-08': number(val(settings, f'Z{row}')),
            },
        }
        categories.append(cat)

    # Map categories to rows in each expense month by exact clean name index order.
    expense_transactions = []
    for m in MONTHS.values():
        month = m['month']
        for offset, row in enumerate(range(m['expense_start'], m['expense_end'] + 1)):
            cat_name = val(expenses, f'A{row}')
            if not cat_name:
                continue
            # Match category key by order first.
            cat = categories[offset] if offset < len(categories) else None
            category_key = cat['key'] if cat else slugify(str(cat_name))
            for day, col in enumerate(DAY_COLS, start=1):
                amount = number(val(expenses, f'{col}{row}'))
                if amount > 0:
                    expense_transactions.append({
                        'date': f'{month}-{day:02d}',
                        'type': 'expense',
                        'person': 'Общее',
                        'category_key': category_key,
                        'amount': round(amount, 2),
                        'comment': f'Импорт из Excel: {cat_name}',
                    })

    income_categories = ['ЗП Артём', 'ЗП Кирилл', 'Доп. заработок', 'Разное (родственники)']
    income_transactions = []
    for m in MONTHS.values():
        month = m['month']
        for idx, row in enumerate(range(m['income_start'], m['income_end'] + 1)):
            source = val(incomes, f'B{row}') or (income_categories[idx] if idx < len(income_categories) else 'Доход')
            for day, col in enumerate(INCOME_DAY_COLS, start=1):
                amount = number(val(incomes, f'{col}{row}'))
                if amount > 0:
                    person = 'Артём' if 'арт' in str(source).lower() else 'Кирилл' if 'кирилл' in str(source).lower() else 'Общее'
                    income_transactions.append({
                        'date': f'{month}-{day:02d}',
                        'type': 'income',
                        'person': person,
                        'category_key': None,
                        'amount': round(amount, 2),
                        'comment': f'Импорт из Excel: {source}',
                    })

    monthly = {}
    for m in MONTHS.values():
        month = m['month']
        # Try planned income from income summary F row.
        if month == '2026-06':
            planned_income = number(val(incomes, 'F25'))
            actual_income = number(val(incomes, 'E25'))
            total_expense = number(val(expenses, 'B28'))
        elif month == '2026-07':
            planned_income = number(val(incomes, 'F36'))
            actual_income = number(val(incomes, 'E36'))
            total_expense = number(val(expenses, 'B61'))
        else:
            planned_income = number(val(incomes, 'F46'))
            actual_income = number(val(incomes, 'E46'))
            total_expense = number(val(expenses, 'B94'))
        planned_expense = sum(cat['plans'].get(month, 0) for cat in categories)
        monthly[month] = {
            'planned_income': planned_income or 172471.65,
            'actual_income': actual_income,
            'planned_expense': round(planned_expense, 2),
            'actual_expense': round(total_expense, 2),
        }

    return {
        'meta': {'source_file': xlsx_path.name, 'generated_for': 'family_budget_bot', 'year_assumption': 2026},
        'users': [
            {'telegram_id': 6902361169, 'name': 'Артём'},
            {'telegram_id': 5242555673, 'name': 'Кирилл'},
        ],
        'settings': {
            'timezone': 'Asia/Novosibirsk',
            'daily_report_time': '23:59',
            'default_guaranteed_income': 172471.65,
            'reserve_percent': 0.10,
        },
        'categories': categories,
        'monthly': monthly,
        'transactions': income_transactions + expense_transactions,
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('xlsx', type=Path)
    parser.add_argument('--out', type=Path, default=Path('data/seed_budget.json'))
    args = parser.parse_args()
    data = build_seed(args.xlsx)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {args.out} with {len(data["categories"])} categories and {len(data["transactions"])} transactions')
