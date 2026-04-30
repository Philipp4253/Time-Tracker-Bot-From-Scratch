# 🕒 Time Tracker Bot From Scratch

**Корпоративный Telegram-бот** для сотрудников и менеджеров, который помогает отслеживать время, затраченное на рабочие проекты.  
Разработан **с нуля** — с интеграцией в Google Sheets, напоминаниями и аналитикой.

---

## 🚀 Основные возможности

- 🧾 Ввод часов, потраченных на проекты  
- 📁 Добавление и удаление проектов  
- 🔄 Редактирование уже внесённых записей  
- ⏰ Утренние и вечерние напоминания внести данные  
- 📊 Автоматическая синхронизация с Google Sheets  
- 📈 Генерация статистики и диаграмм  
- 👥 Аутентификация сотрудников по Telegram username  

---

## 🎬 Демонстрация

Посмотрите короткое видео, показывающее работу бота:

👉 [Смотреть видео (Demo)](https://www.youtube.com/watch?v=Ltn-r5T9la4)

---

## 🧠 Технологии

- Python 3.11  
- `python-telegram-bot`  
- `gspread`, `oauth2client` — интеграция с Google Sheets  
- `APScheduler` — напоминания  
- Google Cloud API  
- Telegram Bot API  

---

## ⚙️ Установка и запуск

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/username/TimeTrackerBotFromScratch.git
   cd TimeTrackerBotFromScratch
   
2. Установить зависимости: pip install -r requirements.txt

3. Добавить service_account.json (Google API ключ) в папку проекта.

4. Запустить бота: python bot.py

👤 Автор

Филипп Высоцкий
📨 Email: filippvys@gmail.com    💬 Telegram: https://t.me/pixel_phil

💡 О проекте

Проект создан для московского рекламного агентство ООО «ФРОМ СКРЭТЧ»!
Показывает навыки разработки Telegram-ботов, работы с API и автоматизацией рутинных процессов.

⭐ Если вам понравился проект — поставьте звёздочку на GitHub!
