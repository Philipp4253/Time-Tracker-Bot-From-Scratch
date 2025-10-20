#!/usr/bin/env python3
# time_tracker_bot.py
import logging
import re
import os
import time
import tempfile
from datetime import datetime, timedelta

import gspread
from gspread.exceptions import APIError, WorksheetNotFound

# matplotlib setup (use non-interactive backend)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode

# ----------------- CONFIG -----------------
GS_SHEET_NAME = "Time-Tracker-Bot"
GS_CREDS_FILE = r"C:\Users\Филипп\Desktop\Shopify\Telegram-bots\time_tracker_bot_fromscratch\service_account.json"

GS_CHART_SHEET_NAME = "Reminders"
GS_DATA_SHEET_NAME = "Records"

# Telegram token (as provided)
TOKEN = "8278469859:AAEsY5JenTL-9SY_U4lALHqVoW3kJ4v1iHM"

# Temporary directory for generated PNGs
TMP_DIR = tempfile.gettempdir()

# ------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Globals for Google Sheets
GS_CLIENT = None
GS_SHEET = None
GS_WORKBOOK = None
GS_SHEET_ID = None
GS_CHART_SHEET_GID = None

logger.info("Initializing Google Sheets connection... (ВЕРСИЯ С АВТОНАСТРОЙКОЙ ДИАГРАММЫ)")

# ---------------- Helper: Google Sheets chart sheet config ----------------
def check_and_configure_chart_sheet():
    """
    Проверяет наличие листа 'Диаграмма', создает его, если нет,
    и настраивает формулу QUERY для агрегации данных (project -> sum(hours)).
    """
    global GS_CHART_SHEET_GID
    if not GS_WORKBOOK:
        logger.error("GS: Workbook is not initialized. Cannot configure chart sheet.")
        return

    try:
        chart_sheet = GS_WORKBOOK.worksheet(GS_CHART_SHEET_NAME)
        GS_CHART_SHEET_GID = chart_sheet.gid
        logger.info(f"GS: Worksheet '{GS_CHART_SHEET_NAME}' found (GID: {GS_CHART_SHEET_GID}).")

        data_range = f"'{GS_DATA_SHEET_NAME}'!E:F"
        query_formula = (
            f'=QUERY({data_range}, '
            f'"SELECT Col1, SUM(Col2) WHERE Col1 IS NOT NULL GROUP BY Col1 LABEL Col1 \'Проект\', SUM(Col2) \'Часы\'",'
            f'1)'
        )

        # Записываем формулу если A1 пуст
        try:
            a1_val = chart_sheet.acell('A1').value
        except Exception:
            a1_val = None

        if not a1_val:
            chart_sheet.update('A1', [[query_formula]], raw=False)
            logger.info(f"GS: Wrote aggregation formula to '{GS_CHART_SHEET_NAME}'!A1.")
        else:
            logger.info(f"GS: '{GS_CHART_SHEET_NAME}'!A1 is not empty. Skipping formula write.")

    except WorksheetNotFound:
        logger.warning(f"GS: Worksheet '{GS_CHART_SHEET_NAME}' not found. Creating new sheet.")
        chart_sheet = GS_WORKBOOK.add_worksheet(title=GS_CHART_SHEET_NAME, rows=100, cols=20)
        GS_CHART_SHEET_GID = chart_sheet.gid

        data_range = f"'{GS_DATA_SHEET_NAME}'!E:F"
        query_formula = (
            f'=QUERY({data_range}, '
            f'"SELECT Col1, SUM(Col2) WHERE Col1 IS NOT NULL GROUP BY Col1 LABEL Col1 \'Проект\', SUM(Col2) \'Часы\'",'
            f'1)'
        )
        chart_sheet.update('A1', [[query_formula]], raw=False)
        logger.info(f"GS: Sheet '{GS_CHART_SHEET_NAME}' created and aggregation formula written.")
    except Exception as e:
        logger.error(f"GS: Error during chart sheet configuration: {e}")


# ---------------- Initialize Google Sheets ----------------
try:
    GS_CLIENT = gspread.service_account(filename=GS_CREDS_FILE)
    gs_workbook = GS_CLIENT.open(GS_SHEET_NAME)
    GS_WORKBOOK = gs_workbook

    try:
        GS_SHEET = gs_workbook.worksheet(GS_DATA_SHEET_NAME)
    except WorksheetNotFound:
        logger.warning(f"GS: Worksheet '{GS_DATA_SHEET_NAME}' not found. Assuming first sheet.")
        GS_SHEET = gs_workbook.sheet1
        GS_DATA_SHEET_NAME = GS_SHEET.title

    GS_SHEET_ID = gs_workbook.id

    check_and_configure_chart_sheet()
    logger.info(f"Successfully connected to Google Sheet: '{GS_SHEET_NAME}'")
except FileNotFoundError:
    logger.error(f"GS_CREDS_FILE not found at: {GS_CREDS_FILE}")
except APIError as e:
    logger.error(f"Failed to open Google Sheet due to API/Auth error (403). Error: {e}")
except Exception as e:
    logger.error(f"General error during Google Sheets initialization: {e}")

# ---------------- Conversation states ----------------
ADD_TIME_PROJECT_SELECT, ADD_TIME_ENTER_HOURS, ADD_TIME_ENTER_COMMENT = range(3)
ADD_PROJECT_NAME = 3
STATISTICS_MENU = 4
SELECT_PROJECT_STATS = 5
END = ConversationHandler.END

# ---------------- Mock projects (you can replace with persistent storage) ----------------
MOCK_PROJECTS = {
    1: "Бизнес модель 80/20",
    2: "Разработка чат бота!",
    3: "Разработка ИИ!",
    4: "Развитие бизнеса!",
}
MOCK_NEXT_PROJECT_ID = 15

# ---------------- Utility ----------------
def escape_html(text: str) -> str:
    text = str(text or "")
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def current_user_identifier_from_update(update: Update) -> str:
    """Возвращает идентификатор пользователя: username (если есть) или 'id_<user_id>'."""
    user = update.effective_user
    if not user:
        return ""
    if user.username:
        return user.username
    return f"id_{user.id}"

# ---------------- Data functions ----------------
def get_projects(user_id):
    """Возвращает список проектов (id, name)."""
    return list(MOCK_PROJECTS.items())

def add_project(user_id, project_name):
    global MOCK_NEXT_PROJECT_ID
    MOCK_PROJECTS[MOCK_NEXT_PROJECT_ID] = project_name
    MOCK_NEXT_PROJECT_ID += 1
    logger.warning(f"MOCK: Project '{project_name}' added.")
    return MOCK_NEXT_PROJECT_ID - 1

def add_time_record(user_id, username, project_id, time_hours, comment, date):
    """
    Записывает запись в Google Sheet (7 колонок):
    id / date/time / user_id / username / project / hours / comment
    """
    project_name = MOCK_PROJECTS.get(project_id, "Неизвестный проект")
    record_id = f"{user_id}_{int(time.time() * 1000)}"
    record_data = [
        record_id,
        date.strftime('%Y-%m-%d %H:%M:%S'),
        str(user_id),
        username,
        project_name,
        f"{time_hours:.2f}",
        comment or ""
    ]
    logger.info(f"GS: Preparing to write record. Length: {len(record_data)}")

    if GS_SHEET:
        if len(record_data) != 7:
            logger.error("GS: Record length mismatch.")
            return False
        try:
            GS_SHEET.append_row(record_data)
            logger.info(f"GS: Time record successfully written: {record_data}")
            return True
        except Exception as e:
            logger.error(f"GS: Failed to write row to sheet: {e}")
            return False
    else:
        logger.warning("GS: Sheet not available. Skipping write.")
        return False

def get_user_records_from_sheet(identifier):
    """
    identifier: int (user_id) or str (username or id_xxx)
    Если identifier - int -> фильтруем по колонке 'user_id'
    Если str -> фильтруем по колонке 'username'
    Возвращает список записей (dict) как возвращает gspread.get_all_records()
    """
    if not GS_SHEET:
        logger.error("GS: Sheet is not initialized.")
        return []

    try:
        all_records = GS_SHEET.get_all_records()
        if isinstance(identifier, int):
            filtered = [r for r in all_records if str(r.get('user_id')) == str(identifier)]
        else:
            # compare to username column
            filtered = [r for r in all_records if str(r.get('username')) == str(identifier)]
        logger.info(f"GS: Retrieved {len(filtered)} records for identifier {identifier}")
        return filtered
    except APIError as e:
        logger.error(f"GS: API Error during data retrieval: {e}")
        return []
    except Exception as e:
        logger.error(f"GS: General error during data retrieval: {e}")
        return []

def calculate_statistics(records, days=None, project_filter=None):
    """
    Возвращает (stats_dict, total_hours).
    stats_dict: {project_name: total_hours}
    Если project_filter указан — ограничиваем только этим проектом.
    """
    stats = {}
    total_hours = 0.0
    start_date = None
    if days is not None:
        now = datetime.now()
        start_date = now - timedelta(days=days - 1)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    for record in records:
        date_str = record.get('date/time')
        try:
            if not date_str or not isinstance(date_str, str):
                raise TypeError("Invalid date string")
            record_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            if start_date and record_date < start_date:
                continue
            project = record.get('project') or "Без проекта"
            if project_filter and project != project_filter:
                continue
            hours_match = re.search(r"(\d+(\.\d+)?)", str(record.get('hours')))
            if hours_match:
                hours = float(hours_match.group(0))
            else:
                raise ValueError("Invalid hours")
            stats[project] = stats.get(project, 0.0) + hours
            total_hours += hours
        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Skipping malformed record: {record}. Error: {e}")
            continue
    return stats, total_hours

# ---------------- Chart generation ----------------
def generate_pie_chart(stats: dict, title: str) -> str:
    """
    Генерирует pie chart PNG из stats и возвращает путь к файлу.
    stats: {label: value}
    """
    if not stats:
        # Generate empty placeholder image
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "Нет данных для диаграммы", ha='center', va='center')
        ax.axis('off')
        filename = os.path.join(TMP_DIR, f"pie_empty_{int(time.time())}.png")
        fig.savefig(filename, bbox_inches='tight')
        plt.close(fig)
        return filename

    labels = []
    sizes = []
    for k, v in stats.items():
        labels.append(str(k))
        sizes.append(float(v))

    # If too many labels, combine small ones into "Другие"
    if len(labels) > 10:
        # combine 10+ into others by sorting descending
        combined = sorted(zip(labels, sizes), key=lambda x: x[1], reverse=True)
        main = combined[:9]
        others = combined[9:]
        labels = [x[0] for x in main] + ["Другие"]
        sizes = [x[1] for x in main] + [sum(x[1] for x in others)]

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
        startangle=90,
        wedgeprops=dict(width=0.5)
    )
    ax.set(aspect="equal")
    ax.set_title(title)
    plt.tight_layout()
    filename = os.path.join(TMP_DIR, f"pie_{int(time.time())}.png")
    fig.savefig(filename, bbox_inches='tight', dpi=150)
    plt.close(fig)
    return filename

# ---------------- Keyboards ----------------
def get_main_menu_keyboard():
    keyboard = [
        ["➕ Внести время", "📝 Редактировать записи"],
        ["📊 Статистика", "⚙️ Настройки"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_main_menu_inline_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Главное меню", callback_data="back_to_main")]])

def get_project_selection_keyboard(user_id, for_stats=False):
    projects = get_projects(user_id)
    keyboard = []
    for project_id, project_name in projects:
        safe_name = escape_html(project_name)
        keyboard.append([InlineKeyboardButton(safe_name, callback_data=f"proj_{project_id}")])
    keyboard.append([InlineKeyboardButton("➕ Добавить проект", callback_data="add_new_project")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_main")])
    if for_stats:
        # additional button to clear project filter
        keyboard.insert(0, [InlineKeyboardButton("🔄 Снять фильтр проекта", callback_data="stats_clear_project")])
    return InlineKeyboardMarkup(keyboard)

def get_comment_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Без комментария", callback_data="no_comment")]])

def get_statistics_keyboard():
    keyboard = [
        [InlineKeyboardButton("📅 Сегодня", callback_data="stats_days_1"),
         InlineKeyboardButton("🗓️ 7 дней", callback_data="stats_days_7")],
        [InlineKeyboardButton("🗓️ 30 дней", callback_data="stats_days_30"),
         InlineKeyboardButton("📊 Всё время", callback_data="stats_days_all")],
        [InlineKeyboardButton("🔍 Выбрать проект", callback_data="stats_choose_project")],
        [InlineKeyboardButton("📈 Открыть Диаграмму (Google Sheets)", callback_data="stats_report_link")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ---------------- Bot handlers ----------------
WELCOME_MESSAGE_TEXT = (
    "🔴Привет 👋 Я помогу отслеживать рабочее время в проектах.\n"
    "— отмечать, сколько часов потрачено,\n"
    "— получать напоминания утром и вечером,\n"
    "— смотреть статистику по проектам.\n\n"
    "Начнём? Жми на кнопку!"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MESSAGE_TEXT)
    return await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # clear temp context
    for k in ['temp_project_id', 'temp_project_name', 'temp_time_hours', 'stats_project_filter']:
        context.user_data.pop(k, None)

    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text("⚙️ Главное меню\n\nВыбери, что будем делать дальше.", reply_markup=None)
        await update.effective_chat.send_message("Нажми на кнопку, чтобы начать.", reply_markup=get_main_menu_keyboard())
    elif update.message:
        await update.message.reply_text("⚙️ Главное меню\n\nНажми на кнопку, чтобы начать.", reply_markup=get_main_menu_keyboard())
    return END

# --- Add time flow ---
async def add_time_entry_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message:
        msg_func = update.message.reply_text
    else:
        q = update.callback_query
        await q.answer()
        msg_func = q.edit_message_text

    await msg_func(
        "⬇️ <b>Шаг 1: Выбери проект</b>\n\nИли добавь новый, чтобы внести время:",
        reply_markup=get_project_selection_keyboard(user_id),
        parse_mode=ParseMode.HTML
    )
    return ADD_TIME_PROJECT_SELECT

async def add_project_step1_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "✍️ <b>Введи название нового проекта</b>:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_project_select")]]),
        parse_mode=ParseMode.HTML
    )
    return ADD_PROJECT_NAME

async def add_project_step2_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    project_name = update.message.text.strip()
    user_id = update.effective_user.id
    add_project(user_id, project_name)
    await update.message.reply_text(f"✅ <b>Проект «{escape_html(project_name)}» добавлен!</b>", parse_mode=ParseMode.HTML)
    await update.message.reply_text("Принято.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    return await add_time_entry_start(update, context)

async def add_time_step2_enter_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    # callback is project id like "1" or "proj_1" depending where from
    try:
        if data.startswith("proj_"):
            project_id = int(data.split("_", 1)[1])
        else:
            project_id = int(data)
    except Exception:
        await q.edit_message_text("❌ Неверный выбор проекта.", reply_markup=get_main_menu_inline_keyboard())
        return END

    project_name = MOCK_PROJECTS.get(project_id, "Неизвестный проект")
    context.user_data['temp_project_id'] = project_id
    context.user_data['temp_project_name'] = project_name

    await q.edit_message_text(
        f"Выбран проект: <b>{escape_html(project_name)}</b>\n\n⏳ <b>Шаг 2: Введи время</b> (например, '2' или '2.5'):",
        parse_mode=ParseMode.HTML,
        reply_markup=None
    )
    await update.effective_chat.send_message("Введи время или нажми '❌ Отмена' для возврата.",
                                             reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True))
    return ADD_TIME_ENTER_HOURS

async def add_time_step2_validate_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = re.sub(r'[,]', '.', update.message.text)
    try:
        time_hours = float(text)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введи число (например, '4' или '1.5').")
        return ADD_TIME_ENTER_HOURS
    if time_hours <= 0:
        await update.message.reply_text("❌ Время должно быть больше нуля.")
        return ADD_TIME_ENTER_HOURS
    context.user_data['temp_time_hours'] = time_hours
    return await add_time_step3_prompt_comment(update, context)

async def add_time_step3_prompt_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("Принято.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    await update.effective_chat.send_message(
        "💬 <b>Шаг 3: Комментарий</b>\n\nВведи краткое описание работы или выбери 'Без комментария':",
        reply_markup=get_comment_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ADD_TIME_ENTER_COMMENT

async def add_time_step4_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username if update.effective_user.username else f"id_{user_id}"

    is_callback = False
    comment = ""
    if update.message:
        comment = update.message.text.strip()
    elif update.callback_query and update.callback_query.data == "no_comment":
        comment = "Без комментария"
        await update.callback_query.answer()
        is_callback = True
    else:
        if update.message and update.message.text:
            comment = update.message.text.strip()
        else:
            comment = "Без комментария"

    project_id = context.user_data.get('temp_project_id')
    project_name = context.user_data.get('temp_project_name')
    time_hours = context.user_data.get('temp_time_hours')

    if not all([project_id, project_name, time_hours]):
        logger.error(f"Context missing: {context.user_data}")
        await update.effective_chat.send_message("❌ Произошла ошибка. Начните заново.",
                                                 reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
        return await main_menu(update, context)

    success = add_time_record(user_id=user_id, username=username, project_id=project_id,
                              time_hours=time_hours, comment=comment, date=datetime.now())

    safe_project_name = escape_html(project_name)
    safe_comment = escape_html(comment)
    review_summary = (
        f"<b>Проект:</b> <code>{safe_project_name}</code>\n"
        f"<b>Время:</b> <b>{time_hours:.2f} ч</b>\n"
        f"<b>Комментарий:</b> <i>{safe_comment}</i>"
    )
    status_text = "✅ <b>Время добавлено!</b>" if success else "❌ <b>Ошибка сохранения!</b>"
    final_message = f"{status_text}\n\n{review_summary}"

    if is_callback:
        await update.callback_query.edit_message_text(final_message,
                                                     reply_markup=get_main_menu_inline_keyboard(),
                                                     parse_mode=ParseMode.HTML)
    else:
        await update.effective_chat.send_message("Принято.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
        await update.effective_chat.send_message(final_message,
                                                 reply_markup=get_main_menu_inline_keyboard(),
                                                 parse_mode=ParseMode.HTML)

    for k in ['temp_project_id', 'temp_project_name', 'temp_time_hours']:
        context.user_data.pop(k, None)
    return END

# ---------------- Statistics flow ----------------
async def statistics_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        msg_func = update.message.reply_text
    else:
        q = update.callback_query
        await q.answer()
        msg_func = q.edit_message_text

    await msg_func("📈 <b>Статистика времени</b>\n\nВыберите период для просмотра:",
                   reply_markup=get_statistics_keyboard(), parse_mode=ParseMode.HTML)
    return STATISTICS_MENU

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Загружаю статистику...")

    identifier = current_user_identifier_from_update(update)
    data = q.data
    days = None
    period_title = "За всё время"

    if data == "stats_days_1":
        days = 1
        period_title = "За сегодня"
    elif data == "stats_days_7":
        days = 7
        period_title = "За последние 7 дней"
    elif data == "stats_days_30":
        days = 30
        period_title = "За последние 30 дней"
    elif data == "stats_days_all":
        days = None
        period_title = "За всё время"
    elif data == "stats_report_link":
        return await send_report_link(update, context)
    elif data == "stats_choose_project":
        # go to project selection (for stats)
        await q.edit_message_text("🔍 Выберите проект для фильтрации статистики:",
                                  reply_markup=get_project_selection_keyboard(update.effective_user.id, for_stats=True))
        return SELECT_PROJECT_STATS
    elif data == "stats_clear_project":
        context.user_data.pop('stats_project_filter', None)
        await q.edit_message_text("✅ Фильтр проекта снят.", reply_markup=get_statistics_keyboard())
        return STATISTICS_MENU

    # Determine identifier type for retrieval
    if identifier.startswith("id_"):
        # fallback - user had no username: filter by numeric user_id stored as string
        # extract numeric id
        try:
            numeric_id = int(identifier.split("_", 1)[1])
            records = get_user_records_from_sheet(numeric_id)
        except Exception:
            records = []
    else:
        # use username
        records = get_user_records_from_sheet(identifier)

    if not records:
        await q.edit_message_text(f"❌ <b>Статистика {period_title}</b>\n\nУ вас нет записей за период.",
                                  reply_markup=get_statistics_keyboard(), parse_mode=ParseMode.HTML)
        return STATISTICS_MENU

    proj_filter = context.user_data.get('stats_project_filter', None)
    stats, total_hours = calculate_statistics(records, days=days, project_filter=proj_filter)

    response_text = f"📊 <b>Статистика {period_title}</b>\n\n"
    if proj_filter:
        response_text = f"📊 <b>Статистика по проекту «{escape_html(proj_filter)}» — {period_title}</b>\n\n"

    if total_hours == 0:
        response_text += "За выбранный период время не найдено."
    else:
        sorted_stats = sorted(stats.items(), key=lambda item: item[1], reverse=True)
        for project, hours in sorted_stats:
            percent = (hours / total_hours) * 100 if total_hours else 0
            project_safe = escape_html(project)
            response_text += f"▪️ <code>{project_safe}</code>\n   — <b>{hours:.2f} ч</b> ({percent:.1f}%)\n"
        response_text += f"\n➡️ <b>Всего: {total_hours:.2f} ч</b>"

    # Edit message with text and keep stats keyboard
    await q.edit_message_text(response_text, reply_markup=get_statistics_keyboard(), parse_mode=ParseMode.HTML)

    # Generate pie chart and send as image
    try:
        img_title = f"Распределение часов — {period_title}"
        if proj_filter:
            img_title = f"{proj_filter} — {period_title}"
        img_path = generate_pie_chart(stats, img_title)
        # send image
        await update.effective_chat.send_photo(photo=open(img_path, 'rb'),
                                              caption=f"📷 Диаграмма: {img_title}")
        # optionally remove file after sending (we'll remove to avoid disk growth)
        try:
            os.remove(img_path)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Failed to generate/send chart: {e}")

    return STATISTICS_MENU

async def select_project_for_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles callback when user selects a project for stats from project keyboard.
    Callback data: proj_<id>
    """
    q = update.callback_query
    await q.answer()
    data = q.data
    if data.startswith("proj_"):
        pid = int(data.split("_", 1)[1])
        pname = MOCK_PROJECTS.get(pid, "Неизвестный проект")
        context.user_data['stats_project_filter'] = pname
        await q.edit_message_text(f"✅ Фильтр применён: <b>{escape_html(pname)}</b>\n\nВыберите период:",
                                  reply_markup=get_statistics_keyboard(),
                                  parse_mode=ParseMode.HTML)
        return STATISTICS_MENU
    elif data == "stats_clear_project":
        context.user_data.pop('stats_project_filter', None)
        await q.edit_message_text("✅ Фильтр проекта снят.", reply_markup=get_statistics_keyboard())
        return STATISTICS_MENU
    else:
        # fallback
        await q.edit_message_text("❌ Неверная команда.", reply_markup=get_statistics_keyboard())
        return STATISTICS_MENU

async def send_report_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not GS_SHEET_ID:
        await q.edit_message_text("❌ Не удалось получить ID Google Таблицы. Проверьте подключение.",
                                  reply_markup=get_statistics_keyboard(), parse_mode=ParseMode.HTML)
        return STATISTICS_MENU
    if GS_CHART_SHEET_GID is not None:
        sheet_url_chart = f"https://docs.google.com/spreadsheets/d/{GS_SHEET_ID}/edit#gid={GS_CHART_SHEET_GID}"
    else:
        sheet_url_chart = f"https://docs.google.com/spreadsheets/d/{GS_SHEET_ID}/edit"

    message_text = (
        "📊 <b>Отчёт</b>\n\n"
        "🔗 Для просмотра статистики в табличном виде и редактирования откройте Google Sheets:\n"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Открыть Google Sheets)", url=sheet_url_chart)],
        [InlineKeyboardButton("⬅️ Назад к статистике", callback_data="back_to_stats_menu")]
    ])
    await q.edit_message_text(message_text, reply_markup=keyboard, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    return STATISTICS_MENU

# ---------------- Cancel / fallback ----------------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for k in ['temp_project_id', 'temp_project_name', 'temp_time_hours', 'stats_project_filter']:
        context.user_data.pop(k, None)

    if update.callback_query:
        q = update.callback_query
        await q.answer("Отменено. Возврат в главное меню.")
        return await main_menu(update, context)
    elif update.message:
        await update.effective_chat.send_message("❌ Отменено.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
        return await main_menu(update, context)
    return END

# ---------------- Main ----------------
def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^➕ Внести время$"), add_time_entry_start),
            MessageHandler(filters.Regex("^📊 Статистика$"), statistics_start),
            CommandHandler("menu", main_menu),
            MessageHandler(filters.Regex("^📝 Редактировать записи$"), main_menu),
            MessageHandler(filters.Regex("^⚙️ Настройки$"), main_menu),
        ],
        states={
            ADD_TIME_PROJECT_SELECT: [
                CallbackQueryHandler(add_time_step2_enter_hours, pattern=r"^(?:\d+|proj_\d+)$"),
                CallbackQueryHandler(add_project_step1_prompt, pattern="^add_new_project$"),
                CallbackQueryHandler(main_menu, pattern="^back_to_main$"),
                CallbackQueryHandler(add_time_entry_start, pattern="^back_to_project_select$"),
            ],
            ADD_PROJECT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_project_step2_save),
            ],
            ADD_TIME_ENTER_HOURS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_time_step2_validate_hours),
            ],
            ADD_TIME_ENTER_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_time_step4_finish),
                CallbackQueryHandler(add_time_step4_finish, pattern="^no_comment$"),
            ],
            STATISTICS_MENU: [
                CallbackQueryHandler(show_statistics, pattern=r"^stats_days_\d+|stats_days_all$"),
                CallbackQueryHandler(send_report_link, pattern="^stats_report_link$"),
                CallbackQueryHandler(main_menu, pattern="^back_to_main$"),
                CallbackQueryHandler(statistics_start, pattern="^back_to_stats_menu$"),
                CallbackQueryHandler(show_statistics, pattern=r"^stats_choose_project$"),
                CallbackQueryHandler(show_statistics, pattern=r"^stats_clear_project$"),
            ],
            SELECT_PROJECT_STATS: [
                CallbackQueryHandler(select_project_for_stats_callback, pattern=r"^proj_\d+$"),
                CallbackQueryHandler(select_project_for_stats_callback, pattern=r"^stats_clear_project$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            CallbackQueryHandler(main_menu, pattern="^back_to_main$"),
            CommandHandler("start", start),
        ],
        allow_reentry=True
    )

    application.add_handler(conv_handler)

    # small global handler to go back from reply-keyboard cancel
    application.add_handler(MessageHandler(filters.Regex("^❌ Отмена$"), main_menu))

    logger.info("Bot started successfully. Waiting for updates...")
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

