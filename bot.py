import os
import telebot
from telebot import types
import schedule
import time
from threading import Thread
import datetime
import pandas as pd
import re
import psycopg2

TOKEN = os.getenv('TELEGRAM_TOKEN') 
DB_URL = os.getenv('DATABASE_URL')
FILE_PATH = '641-12.xlsx'

bot = telebot.TeleBot(TOKEN)

SUBJECTS = {
    "ДсМ": "Дискретная математика",
    "ЗГТ": "Защита государственной тайны",
    "ИП": "Инженерная подготовка",
    "ИЯ": "Иностранный язык",
    "МАД": "Методы анализа данных",
    "МП": "Методы программирования",
    "ПП": "Психология и педагогика",
    "РХБЗ": "Радиационная, химическая и биологическая защита",
    "СУБД": "Системы управления базами данных",
    "ФП": "Физическая подготовка",
    "Э": "Экономика"
}

WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

def init_db():
    if not DB_URL:
        return
    try:
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        chat_id BIGINT PRIMARY KEY
                    );
                """)
                conn.commit()
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")

def add_user(chat_id):
    if not DB_URL:
        return
    try:
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (chat_id) VALUES (%s) ON CONFLICT (chat_id) DO NOTHING;", (chat_id,))
                conn.commit()
    except Exception as e:
        print(f"Ошибка добавления пользователя: {e}")

def get_all_users():
    if not DB_URL:
        return []
    try:
        with psycopg2.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM users;")
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Ошибка получения пользователей: {e}")
        return []

def load_schedule(file_path):
    df = pd.read_excel(file_path, header=None)
    sched = {}
    day_blocks = [(5, 6, 9), (10, 11, 14), (15, 16, 19), (20, 21, 24), (25, 26, 29), (30, 31, 33)]
    
    for col in range(3, df.shape[1]):
        for (date_row, start_row, end_row) in day_blocks:
            date_val = df.iloc[date_row, col]
            if pd.notnull(date_val) and hasattr(date_val, 'strftime'):
                date_str = date_val.strftime('%Y-%m-%d')
                
                day_schedule = []
                day_seminars_names = set()
                day_seminars_full = []
                day_practices_full = []
                
                for r in range(start_row, end_row + 1):
                    class_val = df.iloc[r, col]
                    time_val = df.iloc[r, 2]
                    
                    if pd.notnull(class_val):
                        class_text = str(class_val).strip().replace('\n', ' ')
                        if class_text not in ('', 'NaN', 'nan', 'ПВ', 'ОП', 'Отп', 'Н'):
                            
                            is_seminar = class_text.startswith('С/') or class_text.startswith('С ')
                            is_practice = class_text.startswith('П/') or class_text.startswith('П ')
                            
                            for abbr, full in SUBJECTS.items():
                                if re.search(rf'\b{abbr}\b', class_text):
                                    class_text = re.sub(rf'\b{abbr}\b', full, class_text)
                                    if is_seminar:
                                        day_seminars_names.add(full)
                            
                            if is_seminar:
                                formatted_class = f"👨‍🏫 ⏱ <b>{time_val}</b>: {class_text}"
                                day_seminars_full.append(formatted_class)
                            elif is_practice:
                                formatted_class = f"🛠 ⏱ <b>{time_val}</b>: {class_text}"
                                day_practices_full.append(formatted_class)
                            else:
                                formatted_class = f"⏱ <b>{time_val}</b>: {class_text}"
                                
                            day_schedule.append(formatted_class)
                                
                if day_schedule:
                    sched[date_str] = {
                        'text': "\n\n".join(day_schedule),
                        'seminars_names': list(day_seminars_names),
                        'seminars_full': day_seminars_full,
                        'practices_full': day_practices_full
                    }
    return sched

my_schedule = load_schedule(FILE_PATH)
print(f"✅ Расписание загружено: найдено {len(my_schedule)} учебных дней.")

def format_message(date_str, title_prefix):
    if date_str in my_schedule:
        schedule_text = my_schedule[date_str]['text']
        seminars = my_schedule[date_str]['seminars_names']
        
        msg = f"{title_prefix} <b>({date_str}):</b>\n\n{schedule_text}"
        
        if seminars:
            msg += "\n\n❗️ <b>ОБРАТИТЕ ВНИМАНИЕ:</b>\nСегодня у вас семинар(ы) по предметам:\n🔸 " + "\n🔸 ".join(seminars)
        return msg
    return None

def get_weekly_events(event_type):
    today = datetime.datetime.now()
    monday = today - datetime.timedelta(days=today.weekday())
    
    events_text = []
    for i in range(7):
        curr_date = monday + datetime.timedelta(days=i)
        date_str = curr_date.strftime('%Y-%m-%d')
        
        if date_str in my_schedule:
            day_events = my_schedule[date_str].get(event_type, [])
            if day_events:
                wd = WEEKDAYS[i]
                events_text.append(f"📅 <b>{wd} ({date_str})</b>\n" + "\n".join(day_events))
                
    if events_text:
        return "\n\n".join(events_text)
    return None

def send_schedule_tomorrow():
    try:
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        msg = format_message(tomorrow, "🔔 Расписание на завтра")
        if msg:
            for user_id in get_all_users():
                try:
                    bot.send_message(user_id, msg, parse_mode='HTML')
                except Exception as e:
                    print(f"Ошибка отправки пользователю {user_id}: {e}")
    except Exception as e:
        print(f"Ошибка в send_schedule_tomorrow: {e}")

def send_schedule_today():
    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        msg = format_message(today, "⏰ Доброе утро! Расписание на сегодня")
        if msg:
            for user_id in get_all_users():
                try:
                    bot.send_message(user_id, msg, parse_mode='HTML')
                except Exception as e:
                    print(f"Ошибка отправки пользователю {user_id}: {e}")
    except Exception as e:
        print(f"Ошибка в send_schedule_today: {e}")

schedule.every().day.at("20:00").do(send_schedule_tomorrow)
schedule.every().day.at("07:00").do(send_schedule_today)

def schedule_checker():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print(f"Ошибка в таймере: {e}")
        time.sleep(1)

@bot.message_handler(commands=['start'])
def send_welcome(message):
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

if __name__ == "__main__":
    init_db()
    Thread(target=schedule_checker, daemon=True).start()
    print("Бот запущен и ждёт...")
    bot.polling(none_stop=True)
