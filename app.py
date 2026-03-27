# -*- coding: utf-8 -*-
import os
import json
import time
import threading
import requests
from flask import Flask, request, render_template, session, redirect, url_for
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# ================= 1. إعدادات السيرفر =================
app = Flask(__name__)
app.secret_key = "haraj_telegram_super_secret"
BOT_TOKEN = "8703446111:AAFgOcfn4SbYYZOEPrW4ecqRyaYrPz_LcE4"
bot = telebot.TeleBot(BOT_TOKEN, threaded=False) 
ADMIN_PASSWORD = "123"

# ================= 2. قاعدة البيانات =================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///telegram_haraj.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class TelegramUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active') 
    expiry_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.utcnow() + timedelta(days=7))
    sleep_minutes = db.Column(db.Integer, default=15) 
    search_words = db.Column(db.Text, default='[]') 
    excluded_words = db.Column(db.Text, default='[]')
    quiet_enabled = db.Column(db.Boolean, default=False)
    quiet_start = db.Column(db.String(5), default='00')
    quiet_end = db.Column(db.String(5), default='08')

class AdArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), nullable=False)
    ad_url = db.Column(db.String(500), nullable=False)
    keyword = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ================= 3. مسار استقبال تليجرام =================
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except:
        pass
    return "!", 200

# ================= 4. أزرار وأوامر البوت =================
def get_main_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ إضافة صيدة", callback_data="add_word"),
        InlineKeyboardButton("⛔ استبعاد كلمة", callback_data="add_excluded")
    )
    markup.add(
        InlineKeyboardButton("📋 راداراتي", callback_data="list_words"),
        InlineKeyboardButton("🗑️ حذف", callback_data="delete_word")
    )
    markup.add(
        InlineKeyboardButton("🔇 الهدوء", callback_data="quiet_settings"),
        InlineKeyboardButton("📞 الإدارة", url="https://t.me/Tur100") 
    )
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = str(message.chat.id)
    username = message.from_user.username
    with app.app_context():
        user = TelegramUser.query.filter_by(chat_id=chat_id).first()
        if not user:
            user = TelegramUser(chat_id=chat_id, username=username)
            db.session.add(user)
            db.session.commit()
            text = "مرحباً بك في راصد حراج! 🎯\nتم تسجيلك ومنحك 7 أيام مجانية.\nاختر من القائمة للبدء:"
        else:
            if user.status == 'expired' or user.expiry_date < datetime.utcnow():
                text = "⏳ انتهت فترة اشتراكك. يرجى التواصل مع الإدارة للتجديد."
            else:
                text = "أهلاً بك مجدداً في لوحة التحكم 🎯\nماذا تريد أن تفعل؟"
    bot.reply_to(message, text, reply_markup=get_main_keyboard())

@bot.message_handler(commands=['test'])
def test_cmd(message):
    try:
        keyword = message.text.split(' ', 1)[1].strip()
        bot.reply_to(message, f"⏳ جاري فحص حراج عن '{keyword}' (من الباب الخلفي للتطبيق)...")
        ads = fetch_haraj_ads(keyword, test_mode=True)
        if ads:
            bot.reply_to(message, f"✅ نجح الاختراق! تم العثور على {len(ads)} إعلانات.\n\n📌 {ads[0]['title']}\n🔗 {ads[0]['url']}")
        else:
            bot.reply_to(message, "❌ للأسف، حتى الباب الخلفي تم حظره على سيرفرات ريندر.")
    except:
        bot.reply_to(message, "أرسل الأمر متبوعاً بالكلمة، مثال:\n/test كامري")

@bot.message_handler(commands=['del'])
def delete_word_cmd(message):
    chat_id = str(message.chat.id)
    try:
        word = message.text.split(' ', 1)[1].strip()
        with app.app_context():
            user = TelegramUser.query.filter_by(chat_id=chat_id).first()
            if user:
                words = json.loads(user.search_words)
                if word in words:
                    words.remove(word)
                    user.search_words = json.dumps(words)
                    db.session.commit()
                    bot.reply_to(message, f"✅ تم حذف '{word}' من الرادار.")
                else:
                    bot.reply_to(message, "الكلمة غير موجودة.")
    except:
        bot.reply_to(message, "الصيغة خاطئة. مثال:\n/del كامري")

@bot.message_handler(commands=['del_exc'])
def delete_exc_cmd(message):
    chat_id = str(message.chat.id)
    try:
        word = message.text.split(' ', 1)[1].strip()
        with app.app_context():
            user = TelegramUser.query.filter_by(chat_id=chat_id).first()
            if user:
                words = json.loads(user.excluded_words)
                if word in words:
                    words.remove(word)
                    user.excluded_words = json.dumps(words)
                    db.session.commit()
                    bot.reply_to(message, f"✅ تم حذف '{word}' من قائمة الاستبعاد.")
                else:
                    bot.reply_to(message, "الكلمة غير موجودة.")
    except:
        bot.reply_to(message, "الصيغة خاطئة. مثال:\n/del_exc مصدوم")

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = str(call.message.chat.id)
    with app.app_context():
        user = TelegramUser.query.filter_by(chat_id=chat_id).first()
        if not user or user.status == 'expired' or user.expiry_date < datetime.utcnow():
            bot.answer_callback_query(call.id, "اشتراكك منتهي.", show_alert=True)
            return

        if call.data == "add_word":
            msg = bot.send_message(chat_id, "اكتب الكلمة التي تريد اصطيادها:")
            bot.register_next_step_handler(msg, lambda m: process_add(m, 'search'))
        elif call.data == "add_excluded":
            msg = bot.send_message(chat_id, "اكتب الكلمة التي لا تريد رؤيتها:")
            bot.register_next_step_handler(msg, lambda m: process_add(m, 'exclude'))
        elif call.data == "list_words":
            w = json.loads(user.search_words)
            e = json.loads(user.excluded_words)
            text = "🎯 كلماتك المرصودة:\n" + ("\n".join([f"- {x}" for x in w]) if w else "لا يوجد")
            text += "\n\n⛔ المستبعدة:\n" + ("\n".join([f"- {x}" for x in e]) if e else "لا يوجد")
            bot.send_message(chat_id, text)
        elif call.data == "delete_word":
            bot.send_message(chat_id, "للحذف أرسل:\n/del الكلمة\nأو للمستبعدة:\n/del_exc الكلمة")
        elif call.data == "quiet_settings":
            msg = bot.send_message(chat_id, "🔇 أرسل وقت الهدوء بصيغة (00-08)\nلإلغاء الهدوء أرسل: الغاء")
            bot.register_next_step_handler(msg, process_quiet)
        bot.answer_callback_query(call.id)

def process_add(message, target):
    chat_id = str(message.chat.id)
    word = message.text.strip()
    with app.app_context():
        user = TelegramUser.query.filter_by(chat_id=chat_id).first()
        if user:
            lst = json.loads(user.search_words if target == 'search' else user.excluded_words)
            if len(lst) >= 15:
                bot.send_message(chat_id, "وصلت للحد الأقصى (15).")
                return
            if word not in lst:
                lst.append(word)
                if target == 'search': user.search_words = json.dumps(lst)
                else: user.excluded_words = json.dumps(lst)
                db.session.commit()
                bot.send_message(chat_id, f"✅ تمت إضافة '{word}' بنجاح.", reply_markup=get_main_keyboard())
            else:
                bot.send_message(chat_id, "الكلمة موجودة مسبقاً.")

def process_quiet(message):
    chat_id = str(message.chat.id)
    text = message.text.strip()
    with app.app_context():
        user = TelegramUser.query.filter_by(chat_id=chat_id).first()
        if not user: return
        if text in ['الغاء', 'إلغاء']:
            user.quiet_enabled = False
            db.session.commit()
            bot.send_message(chat_id, "✅ تم إلغاء وقت الهدوء.", reply_markup=get_main_keyboard())
            return
        try:
            s, e = text.split('-')
            s, e = int(s.strip()), int(e.strip())
            if 0 <= s <= 23 and 0 <= e <= 23:
                user.quiet_start, user.quiet_end, user.quiet_enabled = str(s), str(e), True
                db.session.commit()
                bot.send_message(chat_id, f"✅ تم تفعيل الهدوء من {s}:00 إلى {e}:00 بتوقيت السعودية.", reply_markup=get_main_keyboard())
            else:
                bot.send_message(chat_id, "❌ خطأ في الساعات.")
        except:
            bot.send_message(chat_id, "❌ صيغة خاطئة.")

# ================= 5. محرك الرادار (الباب الخلفي للتطبيق) =================
LAST_RUNS = {}

def fetch_haraj_ads(keyword, test_mode=False):
    url = "https://graphql.haraj.com.sa/"
    # تمويه قوي: ندخل على أساس إننا تطبيق حراج الرسمي في جهاز آيفون
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Haraj/6.11.2 (iPhone; iOS 16.6; Scale/3.00)",
        "Accept": "application/json"
    }
    
    # لغة استعلام حراج الخاصة (GraphQL)
    query = """
    query($query: String, $page: Int) {
      search(query: $query, page: $page) {
        items {
          id
          title
        }
      }
    }
    """
    
    ads = []
    pages = 1 if test_mode else 3 
    
    for page in range(1, pages + 1):
        payload = {
            "query": query,
            "variables": {
                "query": keyword,
                "page": page
            }
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=15)
            if res.status_code == 200:
                data = res.json()
                items = data.get("data", {}).get("search", {}).get("items", [])
                for item in items:
                    title = item.get("title", "")
                    # بناء الرابط الخاص بالإعلان من الـ ID
                    link = f"https://haraj.com.sa/11{item.get('id')}"
                    
                    ad_data = {'title': title, 'url': link}
                    if ad_data not in ads:
                        ads.append(ad_data)
        except Exception as e:
            pass
        if not test_mode: time.sleep(2) 
    return ads

def radar_engine():
    time.sleep(10)
    while True:
        try:
            with app.app_context():
                users = TelegramUser.query.filter_by(status='active').all()
                now = datetime.utcnow()
                ksa_time = now + timedelta(hours=3)
                ch = ksa_time.hour
                for user in users:
                    if user.expiry_date < now:
                        user.status = 'expired'
                        db.session.commit()
                        continue
                    if user.quiet_enabled:
                        sh, eh = int(user.quiet_start), int(user.quiet_end)
                        if (sh < eh and sh <= ch < eh) or (sh >= eh and (ch >= sh or ch < eh)):
                            continue 
                        
                    last_run = LAST_RUNS.get(user.chat_id)
                    if not last_run or (now - last_run).total_seconds() >= (user.sleep_minutes * 60):
                        LAST_RUNS[user.chat_id] = now
                        w_list = json.loads(user.search_words)
                        e_list = json.loads(user.excluded_words)
                        for word in w_list:
                            ads = fetch_haraj_ads(word)
                            for ad in ads:
                                if any(exc in ad['title'] for exc in e_list):
                                    continue
                                if not AdArchive.query.filter_by(chat_id=user.chat_id, ad_url=ad['url']).first():
                                    try:
                                        # استبدلنا إرسال الصورة برسالة نصية عادية عشان التليجرام يجيب معاينة الإعلان (وصورته) بشكل تلقائي!
                                        bot.send_message(user.chat_id, f"🎯 صيدة: {word}\n📌 {ad['title']}\n🔗 {ad['url']}")
                                        db.session.add(AdArchive(chat_id=user.chat_id, ad_url=ad['url'], keyword=word))
                                        db.session.commit()
                                    except: pass
        except: pass
        time.sleep(30)

threading.Thread(target=radar_engine, daemon=True).start()

# ================= 6. لوحة الإدارة =================
@app.route('/')
def index(): return redirect(url_for('admin_panel'))

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        return "كلمة المرور خاطئة", 401
    users = TelegramUser.query.all()
    archives = AdArchive.query.order_by(AdArchive.timestamp.desc()).limit(50).all()
    return render_template('admin.html', users=users, archives=archives)

@app.route('/admin/update/<int:user_id>', methods=['POST'])
def admin_update_user(user_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_panel'))
    user = TelegramUser.query.get_or_404(user_id)
    add_days = request.form.get('add_days')
    if add_days and int(add_days) > 0:
        user.expiry_date = max(user.expiry_date, datetime.utcnow()) + timedelta(days=int(add_days))
        user.status = 'active'
        try: bot.send_message(user.chat_id, "🎉 تم تجديد اشتراكك بنجاح!")
        except: pass
    sleep_mins = request.form.get('sleep_minutes')
    if sleep_mins and int(sleep_mins) > 0: user.sleep_minutes = int(sleep_mins)
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_panel'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
