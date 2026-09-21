import razorpay
from flask import Flask, request
import telebot

TOKEN = '8203717604:AAFToIEk11Le36Dg8pKxGSrLqH_bwlconJA'
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Razorpay Client (Yahan apni Test ya Live Key ID aur Secret dalein)
razorpay_client = razorpay.Client(auth=("rzp_test_TeqKl9A9tWKnZI", "wLcq7AuD25CXDasBXn1teMAg"))

# Step 1: User jab /addfunds dabaye
@bot.message_handler(commands=['addfunds'])
def ask_amount(message):
    msg = bot.reply_to(message, "💰 **Kitna amount add karna chahte hain?**\n(Minimum ₹10 hona chahiye)")
    # Agla message user ka amount hoga, isliye use process_amount function par bhej rahe hain
    bot.register_next_step_handler(msg, process_payment_amount)

# Step 2: User dwara bheja gaya amount check karna aur link banana
def process_payment_amount(message):
    try:
        user_input = message.text.strip()
        amount_rs = float(user_input)
        
        # Minimum amount validation (₹10)
        if amount_rs < 10:
            bot.reply_to(message, "❌ Minimum amount ₹10 hai. Kripya ₹10 ya usse zyada enter karein. Dubara koshish karne ke liye /addfunds dabayein.")
            return

        # Amount ko paise me convert karna (Jaise ₹10 = 1000 paise)
        amount_paise = int(amount_rs * 100)

        # Razorpay payment link data
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "accept_partial": False,
            "description": f"Add ₹{amount_rs} to SMM Bot Wallet",
            "customer": {
                "name": str(message.from_user.first_name),
                "contact": "9876543210",
                "email": "user@example.com"
            },
            "notify": {"sms": False, "email": False},
            "notes": {"telegram_user_id": str(message.from_user.id)}
        }
        
        # Razorpay se link generate karein
        payment_link = razorpay_client.payment_link.create(data)
        short_url = payment_link.get('short_url')
        
        bot.reply_to(message, f"💳 **Aapka payment link taiyar hai:**\n\n🔗 {short_url}\n\n*Payment poori karne ke baad aapka balance update ho jayega.*")
    
    except ValueError:
        bot.reply_to(message, "❌ Kripya sirf valid number enter karein (jaise: 50, 100). Dubara try karne ke liye /addfunds dabayein.")
    except Exception as e:
        bot.reply_to(message, f"Kuch error aa gaya: {str(e)}")

@app.route('/')
def home():
    return "SMM Bot with Razorpay is running!"

if __name__ == '__main__':
    import threading
    def run_flask():
        app.run(host='0.0.0.0', port=10000)
    
    t = threading.Thread(target=run_flask)
    t.start()
    
    bot.infinity_polling()


import telebot
from telebot import types
import requests
import sqlite3
import time
from datetime import datetime
import os
from flask import Flask
from threading import Thread

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8203717604:AAFToIEk11Le36Dg8pKxGSrLqH_bwlconJA"          
SMM_API_URL = "https://smmwiz.com/api/v2"  
SMM_API_KEY = "d0ee8a3432a6770f9a6003181d308d72"        

ADMIN_ID = 6658716591                           # Jaise: 123456789
UPI_ID = "arshad79@ptyes"                        
QR_CODE_URL = "https://cdn.phototourl.com/free/2026-09-21-dffdef71-44c0-487e-add8-9e00412d2593.jpg"
ADMIN_USERNAME = "@@Socialpookiehelp"           
# =======================================================

bot = telebot.TeleBot(BOT_TOKEN)
user_order_state = {}

# ================= FLASK SERVER FOR RENDER =================
app = Flask('')

@app.route('/')
def home():
    return "Bot is active and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ================= HELPER DATABASE FUNCTIONS =================
def get_db_connection():
    return sqlite3.connect('smm_database.db', check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0.0
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value REAL
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id TEXT,
        user_id INTEGER,
        service_name TEXT,
        link TEXT,
        quantity INTEGER,
        cost REAL,
        date_time TEXT
    )
    ''')
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('profit_margin', 40.0)")
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def register_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0.0)", (user_id,))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def get_profit_margin():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'profit_margin'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 40.0

def set_profit_margin(new_margin):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'profit_margin'", (new_margin,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def save_order(order_id, user_id, service_name, link, quantity, cost):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", 
                   (str(order_id), user_id, service_name, link, quantity, cost, now))
    conn.commit()
    conn.close()

def calculate_selling_price(wholesale_rate):
    wholesale_rate = float(wholesale_rate)
    margin_percent = get_profit_margin()
    selling_price = wholesale_rate + (wholesale_rate * (margin_percent / 100.0))
    return round(selling_price, 2)

def clear_user_state(user_id):
    if user_id in user_order_state:
        del user_order_state[user_id]

# ================= KEYBOARDS =================
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton("🛍 Select Platform")
    btn2 = types.KeyboardButton("💰 My Balance")
    btn3 = types.KeyboardButton("📜 My Orders")
    btn4 = types.KeyboardButton("💳 Add Funds (QR & UPI)")
    btn5 = types.KeyboardButton("📞 Support")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

def platforms_inline_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    b0 = types.InlineKeyboardButton("👑 IG Followers Only", callback_data="plat_ig_followers")
    b1 = types.InlineKeyboardButton("📸 Instagram All", callback_data="plat_instagram")
    b2 = types.InlineKeyboardButton("✈️ Telegram", callback_data="plat_telegram")
    b3 = types.InlineKeyboardButton("▶️ YouTube", callback_data="plat_youtube")
    b4 = types.InlineKeyboardButton("📘 Facebook", callback_data="plat_facebook")
    b5 = types.InlineKeyboardButton("🐦 Twitter (X)", callback_data="plat_twitter")
    b6 = types.InlineKeyboardButton("💬 WhatsApp", callback_data="plat_whatsapp")
    
    markup.add(b0)
    markup.add(b1, b2, b3, b4, b5, b6)
    return markup

# ================= COMMAND HANDLERS =================

@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    clear_user_state(user_id)
    register_user(user_id)
    welcome_text = (
        f"✨ **Namaste {message.from_user.first_name}!** ✨\n\n"
        f"Welcome to Social Media Services Bot!\n"
        f"Niche diye gaye buttons se apna platform select karein aur orders lagayein."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=main_menu())

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "⚠️ **Usage:** `/broadcast Aapka Message Yahan Write Karein`", parse_mode="Markdown")
        return

    all_users = get_all_users()
    success_count = 0
    fail_count = 0

    bot.reply_to(message, f"📢 Broadcast start ho raha hai... (Total Users: {len(all_users)})")

    for u_id in all_users:
        try:
            bot.send_message(u_id, f"📢 **Announcement / Special Offer:**\n\n{msg_text}", parse_mode="Markdown")
            success_count += 1
        except Exception:
            fail_count += 1

    bot.send_message(message.chat.id, f"✅ **Broadcast Completed!**\n\n🟢 Success: {success_count}\n🔴 Failed/Blocked: {fail_count}")

@bot.message_handler(commands=['setmargin'])
def change_margin(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, f"Current Margin: `{get_profit_margin()}%`\nUsage: `/setmargin 40`")
            return
        set_profit_margin(float(args[1]))
        bot.reply_to(message, f"✅ Profit Margin updated to **{args[1]}%**!")
    except Exception:
        bot.reply_to(message, "Error updating margin.")

@bot.message_handler(commands=['addbalance'])
def add_user_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        target_user = int(args[1])
        amount = float(args[2])
        update_balance(target_user, amount)
        bot.reply_to(message, f"✅ Added ₹{amount} to User `{target_user}`")
        bot.send_message(target_user, f"🎉 Admin has added ₹{amount} to your bot wallet!")
    except Exception:
        bot.reply_to(message, "Usage: `/addbalance <user_id> <amount>`")

@bot.message_handler(func=lambda message: message.text in ["🛍 Select Platform", "💰 My Balance", "📜 My Orders", "💳 Add Funds (QR & UPI)", "📞 Support"])
def handle_menu_buttons(message):
    user_id = message.from_user.id
    text = message.text
    clear_user_state(user_id)
    register_user(user_id)

    if text == "🛍 Select Platform":
        bot.send_message(message.chat.id, "👇 **Kiski service chahiye? Niche select karein:**", parse_mode="Markdown", reply_markup=platforms_inline_menu())

    elif text == "💰 My Balance":
        user_data = get_user(user_id)
        bal = user_data[0] if user_data else 0.0
        bot.reply_to(message, f"👤 **User ID:** `{user_id}`\n💰 **Current Balance:** ₹{bal:.2f}", parse_mode="Markdown")

    elif text == "📜 My Orders":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT order_id, service_name, quantity, cost, date_time FROM orders WHERE user_id = ? ORDER BY rowid DESC LIMIT 5", (user_id,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            bot.reply_to(message, "📜 **Aapne abhi tak koi order nahi lagaya hai.**", parse_mode="Markdown")
        else:
            msg = "📜 **Aapke Recent 5 Orders:**\n\n"
            for row in rows:
                msg += f"🆔 **Order ID:** `{row[0]}`\n📦 **Service:** {row[1]}\n🔢 **Qty:** {row[2]}\n💰 **Cost:** ₹{row[3]}\n📅 **Date:** {row[4]}\n---------------------------\n"
            bot.reply_to(message, msg, parse_mode="Markdown")

    elif text == "💳 Add Funds (QR & UPI)":
        fund_text = (
            f"💳 **Add Funds**\n\n"
            f"1️⃣ QR Code scan karein ya UPI ID par payment karein:\n"
            f"👉 **UPI ID:** `{UPI_ID}`\n\n"
            f"2️⃣ Payment karne ke baad screenshot/UTR Admin ko bhejein.\n"
            f"3️⃣ Admin instant wallet update kar dega.\n\n"
            f"📞 **Admin:** {ADMIN_USERNAME}"
        )
        try:
            bot.send_photo(message.chat.id, photo=QR_CODE_URL, caption=fund_text, parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, fund_text, parse_mode="Markdown")

    elif text == "📞 Support":
        bot.send_message(message.chat.id, f"🤝 **Support Admin:** {ADMIN_USERNAME}\n\nKisi bhi dikkat ke liye Admin ko direct message karein.")

# ================= CALLBACK QUERY =================

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if call.data.startswith("plat_"):
        platform_name = call.data.replace("plat_", "").lower()
        bot.answer_callback_query(call.id, "Loading services...")

        try:
            payload = {'key': SMM_API_KEY, 'action': 'services'}
            services = requests.post(SMM_API_URL, data=payload).json()

            matched = []

            if platform_name == "ig_followers":
                for s in services:
                    cat = s.get('category', '').lower()
                    s_name = s.get('name', '').lower()
                    if ("instagram" in cat or "ig" in cat or "instagram" in s_name or "ig" in s_name) and ("follower" in cat or "follower" in s_name):
                        matched.append(s)
            else:
                keywords = [platform_name]
                if platform_name == "instagram":
                    keywords = ["instagram", "ig"]

                for s in services:
                    cat = s.get('category', '').lower()
                    s_name = s.get('name', '').lower()
                    if any(k in cat or k in s_name for k in keywords):
                        matched.append(s)

            if not matched:
                bot.send_message(chat_id, "❌ Currently no services found for this category.")
                return

            markup = types.InlineKeyboardMarkup(row_width=1)
            for s in matched[:15]:
                selling_price = calculate_selling_price(s.get('rate', 0))
                btn_text = f"{s.get('name')} - ₹{selling_price}/1K"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"buy_{s.get('service')}"))

            title = "Instagram Followers" if platform_name == "ig_followers" else platform_name.title()
            bot.send_message(chat_id, f"📋 **{title} Services:**\nNiche apni pasand ki service par click karein:", parse_mode="Markdown", reply_markup=markup)

        except Exception:
            bot.send_message(chat_id, "⚠️ Error fetching services from SMM panel.")

    elif call.data.startswith("buy_"):
        service_id = call.data.replace("buy_", "")
        user_order_state[user_id] = {'service_id': service_id, 'step': 'wait_link'}

        msg = bot.send_message(chat_id, "🔗 **Apna Link bhejein:**\n(Jaise Post Link, Profile Link ya Channel Link)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_link)

# ================= ORDER PROCESS =================

def process_link(message):
    user_id = message.from_user.id
    
    if message.text in ["🛍 Select Platform", "💰 My Balance", "📜 My Orders", "💳 Add Funds (QR & UPI)", "📞 Support"]:
        handle_menu_buttons(message)
        return

    if user_id in user_order_state and user_order_state[user_id].get('step') == 'wait_link':
        user_order_state[user_id]['link'] = message.text
        user_order_state[user_id]['step'] = 'wait_qty'

        msg = bot.send_message(message.chat.id, "🔢 **Kitni Quantity chahiye?**\n(Number type karein, e.g. 1000)", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_qty)

def process_qty(message):
    user_id = message.from_user.id

    if message.text in ["🛍 Select Platform", "💰 My Balance", "📜 My Orders", "💳 Add Funds (QR & UPI)", "📞 Support"]:
        handle_menu_buttons(message)
        return

    if user_id in user_order_state and user_order_state[user_id].get('step') == 'wait_qty':
        try:
            qty = int(message.text)
            service_id = user_order_state[user_id]['service_id']
            link = user_order_state[user_id]['link']

            payload = {'key': SMM_API_KEY, 'action': 'services'}
            services = requests.post(SMM_API_URL, data=payload).json()
            selected = next((s for s in services if str(s.get('service')) == service_id), None)

            if not selected:
                bot.send_message(message.chat.id, "❌ Service not found.")
                clear_user_state(user_id)
                return

            rate = calculate_selling_price(selected.get('rate', 0))
            total_cost = round((rate / 1000.0) * qty, 2)

            user_data = get_user(user_id)
            user_bal = user_data[0] if user_data else 0.0

            if user_bal < total_cost:
                bot.send_message(message.chat.id, f"❌ **Balance Kam Hai!**\n\nIs order ka cost: ₹{total_cost}\nAapka balance: ₹{user_bal}\n\nPehle 'Add Funds' button se balance add karein.")
                clear_user_state(user_id)
                return

            order_payload = {
                'key': SMM_API_KEY,
                'action': 'add',
                'service': service_id,
                'link': link,
                'quantity': qty
            }
            res = requests.post(SMM_API_URL, data=order_payload).json()

            if "order" in res:
                update_balance(user_id, -total_cost)
                save_order(res['order'], user_id, selected.get('name'), link, qty, total_cost)
                bot.send_message(message.chat.id, f"🎉 **Order Placed Successfully!**\n\n📌 Order ID: `{res['order']}`\n💰 Cost: ₹{total_cost}\n📊 Service: {selected.get('name')}", parse_mode="Markdown")
                
                try:
                    bot.send_message(ADMIN_ID, f"🔔 **New Order Placed!**\nUser: `{user_id}`\nService: {selected.get('name')}\nCost: ₹{total_cost}\nOrder ID: `{res['order']}`", parse_mode="Markdown")
                except Exception:
                    pass
            else:
                bot.send_message(message.chat.id, f"❌ Order Error: {res.get('error', 'Unknown Error')}")

            clear_user_state(user_id)

        except ValueError:
            bot.send_message(message.chat.id, "❌ Valid Number dalein (e.g. 500, 1000).")
            msg = bot.send_message(message.chat.id, "🔢 **Dobara Quantity dalein (sirf numbers):**")
            bot.register_next_step_handler(msg, process_qty)

# ================= RUN MAIN THREADS =================
if __name__ == '__main__':
    keep_alive()
    
    while True:
        try:
            print("Bot is running...")
            bot.polling(non_stop=True, interval=1, timeout=60)
        except Exception as e:
            print(f"Network error: {e}. Retrying in 5 seconds...")
            time.sleep(5)
