# --- Константы Telegram API ---
# Вставьте сюда токен вашего Telegram-бота, полученный от BotFather.
BOT_TOKEN = "8278469859:AAEsY5JenTL-9SY_U4lALHqVoW3kJ4v1iHM" 

# --- Константы Google Sheets ---
# Имя файла JSON с ключом сервисного аккаунта. 
# Замените на путь к вашему файлу (например, 'service_account.json').
SERVICE_ACCOUNT_FILE = "timetrackerbot@time-tracker-bot-472613.iam.gserviceaccount.com"

# Имя вашей Google Таблицы (как она называется в Drive)
SPREADSHEET_NAME = "Time-Tracker-Bot"

# !!! ВАЖНО: Вставьте ID вашей Google Таблицы !!!
# ID находится в URL-адресе между /d/ и /edit: 
# https://docs.google.com/spreadsheets/d/ID_ВАШЕЙ_ТАБЛИЦЫ/edit
SPREADSHEET_ID = "1LJHZMGnPwgxXfN09ISFiqIGbzzznc9FAy-rETMr0X84" 

# Имена рабочих листов в Таблице
RECORDS_SHEET_NAME = "Records"
PROJECTS_SHEET_NAME = "Projects"

# --- Прочие константы ---
# Chat ID для административных уведомлений (если нужно)
ADMIN_CHAT_ID = None

# Имя листа, который будет использоваться для агрегированной статистики/диаграммы
CHART_SHEET_NAME = "Диаграмма"
