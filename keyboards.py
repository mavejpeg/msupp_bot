from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def channel_selection():
    buttons = [
        [InlineKeyboardButton("Лайфстайл", callback_data="ch:1")],
        [InlineKeyboardButton("Веб-дизайн", callback_data="ch:2")],
        [InlineKeyboardButton("Новости", callback_data="ch:3")],
    ]
    return InlineKeyboardMarkup(buttons)

def ai_options():
    buttons = [
        [InlineKeyboardButton("✨ Улучшить текст", callback_data="ai_improve")],
        [InlineKeyboardButton("Оставить как есть", callback_data="ai_skip")],
    ]
    return InlineKeyboardMarkup(buttons)

def ai_compare():
    buttons = [
        [InlineKeyboardButton("Взять улучшенный", callback_data="take_improved")],
        [InlineKeyboardButton("Оставить оригинал", callback_data="take_original")],
    ]
    return InlineKeyboardMarkup(buttons)

def preview_actions():
    buttons = [
        [InlineKeyboardButton("📤 Опубликовать сейчас", callback_data="publish_now")],
        [InlineKeyboardButton("🕐 Запланировать", callback_data="schedule")],
        [InlineKeyboardButton("✏️ Изменить", callback_data="edit")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(buttons)

def date_selection(dates):
    # dates - список дат в формате DD.MM (например "12.05")
    keyboard = []
    row = []
    for i, d in enumerate(dates):
        row.append(InlineKeyboardButton(d, callback_data=f"date:{d}"))
        if (i+1) % 7 == 0 or i == len(dates)-1:
            keyboard.append(row)
            row = []
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="back_to_preview")])
    return InlineKeyboardMarkup(keyboard)

def time_selection():
    times = ["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"]
    keyboard = []
    row = []
    for i, t in enumerate(times):
        row.append(InlineKeyboardButton(t, callback_data=f"time:{t}"))
        if (i+1) % 4 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("Другое время", callback_data="custom_time")])
    keyboard.append([InlineKeyboardButton("« Назад к датам", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(keyboard)

def queue_post_actions(post_id):
    buttons = [
        [InlineKeyboardButton("👁 Посмотреть", callback_data=f"viewpost:{post_id}")],
        [InlineKeyboardButton("✏️ Изменить время", callback_data=f"changetime:{post_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"deletepost:{post_id}")],
    ]
    return InlineKeyboardMarkup(buttons)

def confirm_delete(post_id):
    buttons = [
        [InlineKeyboardButton("Да, удалить", callback_data=f"confirmdelete:{post_id}")],
        [InlineKeyboardButton("Нет", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(buttons)