import os
import telebot
from telebot import types
import schedule
import time
from threading import Thread
import datetime
import pandas as pd
import re
import psycopg2 # Библиотека для работы с PostgreSQL

TOKEN = os.getenv('TELEGRAM_TOKEN') 
DB_URL = os.getenv('DATABASE_URL') # Ссылка на базу данных из секретов GitHub
FILE_PATH = '641-12.xlsx'

bot = telebot.TeleBot(TOKEN)

# --- РАБОТА С БАЗОЙ ДАННЫХ POSTGRESQL ---
def init_db():
    """Создает таблицу пользователей, если её еще нет"""
    if not DB_URL:
        return
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT PRIMARY KEY
                );
            """)
            conn.commit()

def add_user(chat_id):
    """Добавляет нового пользователя в базу"""
    if not DB_URL:
        return
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            # ON CONFLICT DO NOTHING защищает от дубликатов, если пользователь нажмет /start дважды
            cur.execute("INSERT INTO users (chat_id) VALUES (%s) ON CONFLICT (chat_id) DO NOTHING;", (chat_id,))
            conn.commit()

def get_all_users():
    """Получает список всех ID пользователей"""
    if not DB_URL:
        return []
    with psycopg2.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM users;")
            return [row[0] for row in cur.fetchall()]

# Инициализируем базу при запуске бота
init_db()


# --- ОБНОВЛЕННЫЕ ФУНКЦИИ РАССЫЛКИ ---
def send_schedule_tomorrow():
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    msg = format_message(tomorrow, "🔔 Расписание на завтра")
    if msg:
        users = get_all_users()
        for user_id in users:
            try:
                bot.send_message(user_id, msg, parse_mode='HTML')
            except Exception as e:
                # Если человек заблокировал бота, просто выводим ошибку и идем дальше
                print(f"Ошибка отправки пользователю {user_id}: {e}")

def send_schedule_today():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    msg = format_message(today, "⏰ Доброе утро! Расписание на сегодня")
    if msg:
        users = get_all_users()
        for user_id in users:
            try:
                bot.send_message(user_id, msg, parse_mode='HTML')
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_id}: {e}")

# ... (таймеры schedule оставляем без изменений) ...

# --- ОБНОВЛЕННАЯ КОМАНДА /START ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Сохраняем chat_id пользователя в базу данных
    add_user(message.chat.id)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_today = types.KeyboardButton("Сегодня")
    btn_tomorrow = types.KeyboardButton("Завтра")
    btn_day_after = types.KeyboardButton("🟢 Послезавтра")
    btn_seminars = types.KeyboardButton("🔵 Семинары на неделе")
    btn_practices = types.KeyboardButton("🔴 Практики на неделе")
    
    markup.add(btn_today, btn_tomorrow)
    markup.add(btn_day_after)
    markup.add(btn_seminars)
    markup.add(btn_practices)
    
    bot.reply_to(message, "Привет! Я бот с расписанием. Я автоматически присылаю уведомления в 20:00 и 07:00.\nВоспользуйтесь кнопками ниже 👇", reply_markup=markup)

# ... (остальные функции handle_text и polling оставляем без изменений) ...

@bot.message_handler(content_types=['text'])
def handle_text(message):
    text = message.text.lower().strip()
    today_date = datetime.datetime.now()
    
    if text in ["сегодня", "/today"]:
        today_str = today_date.strftime('%Y-%m-%d')
        msg = format_message(today_str, "📚 На сегодня")
        bot.reply_to(message, msg if msg else "Сегодня пар нет! 🎉", parse_mode='HTML')
            
    elif text in ["завтра", "/tomorrow"]:
        tomorrow_str = (today_date + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        msg = format_message(tomorrow_str, "📚 На завтра")
        bot.reply_to(message, msg if msg else "Завтра пар нет! 🎉", parse_mode='HTML')
        
    elif "послезавтра" in text:
        day_after_str = (today_date + datetime.timedelta(days=2)).strftime('%Y-%m-%d')
        msg = format_message(day_after_str, "🚀 На послезавтра")
        bot.reply_to(message, msg if msg else "Послезавтра пар нет! 🎉", parse_mode='HTML')
        
    elif "семинары на неделе" in text:
        msg = get_weekly_events('seminars_full')
        if msg:
            bot.reply_to(message, f"🔵 <b>Семинары на этой неделе:</b>\n\n{msg}", parse_mode='HTML')
        else:
            bot.reply_to(message, "На этой неделе семинаров нет! 🥳")
            
    elif "практики на неделе" in text:
        msg = get_weekly_events('practices_full')
        if msg:
            bot.reply_to(message, f"🔴 <b>Практики на этой неделе:</b>\n\n{msg}", parse_mode='HTML')
        else:
            bot.reply_to(message, "На этой неделе практических занятий нет! 🥳")
            
    else:
        bot.reply_to(message, "Пожалуйста, используйте кнопки внизу экрана 👇")
def schedule_checker():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    if not TOKEN:
        print("ОШИБКА: Токен не найден. Убедитесь, что вы добавили TELEGRAM_TOKEN в Secrets and variables на GitHub.")
    else:
        Thread(target=schedule_checker, daemon=True).start()
        print("Бот запущен и ждёт...")
        bot.polling(none_stop=True)
if __name__ == "__main__":
    init_db()
    Thread(target=schedule_checker, daemon=True).start()
    print("Бот запущен и ждёт...")
    bot.polling(none_stop=True)

