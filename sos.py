import os
from datetime import datetime
from flask import Flask, render_template_string, request
import psycopg2
from urllib.parse import urlparse
import razorpay
import requests
import telebot
from telebot import types

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8203717604:AAEXt0oAR7FDbSoQ4pBZTZxXEQwJp6WyMOc"
RENDER_URL = "https://smm-telegram-bot-w9s6.onrender.com"

SMM_API_URL = "https://smmwiz.com/api/v2"
SMM_API_KEY = "d0ee8a3432a6770f9a6003181d308d72"

ADMIN_ID = 6658716591
UPI_ID = "arshad79@ptyes"
QR_CODE_URL = (
    "https://cdn.phototourl.com/free/2026-09-21-dffdef71-44c0-487e-add8-9e00412d2593.jpg"
)
ADMIN_USERNAME = "@Socialpookiehelp"

# Razorpay Credentials
RAZORPAY_KEY_ID = "rzp_test_TeqKl9A9tWKnZI"
RAZORPAY_KEY_SECRET = "wLcq7AuD25CXDasBXn1teMAg"

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
user_order_state = {}

MENU_BUTTONS = [
    "🛍 Select Platform",
    "💰 My Balance",
    "📜 My Orders",
    "💳 Add Funds (QR & UPI)",
    "📞 Support",
]

# ==================== DATABASE SETUP (POSTGRESQL / SUPABASE) ====================
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
  if DATABASE_URL:
    return psycopg2.connect(DATABASE_URL)
  else:
    raise ValueError("DATABASE_URL environment variable is not set!")


def init_db():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, balance"
      " REAL DEFAULT 0.0)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)"
  )
  cursor.execute(
      "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, order_id TEXT,"
      " user_id BIGINT, service_name TEXT, link TEXT, quantity INTEGER, cost"
      " REAL, date_time TEXT)"
  )
  cursor.execute(
      "INSERT INTO settings (key, value) VALUES ('profit_margin', 40.0) ON"
      " CONFLICT (key) DO NOTHING"
  )
  conn.commit()
  cursor.close()
  conn.close()


init_db()


# ==================== HELPER FUNCTIONS ====================
def get_user(user_id):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
  row = cursor.fetchone()
  cursor.close()
  conn.close()
  return row


def register_user(user_id):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO users (user_id, balance) VALUES (%s, 0.0) ON CONFLICT"
      " (user_id) DO NOTHING",
      (user_id,),
  )
  conn.commit()
  cursor.close()
  conn.close()


def update_balance(user_id, amount):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "UPDATE users SET balance = balance + %s WHERE user_id = %s",
      (amount, user_id),
  )
  conn.commit()
  cursor.close()
  conn.close()


def get_profit_margin():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute("SELECT value FROM settings WHERE key = 'profit_margin'")
  row = cursor.fetchone()
  cursor.close()
  conn.close()
  return row[0] if row else 40.0


def calculate_selling_price(wholesale_rate):
  wholesale_rate = float(wholesale_rate)
  margin_percent = get_profit_margin()
  return round(
      wholesale_rate + (wholesale_rate * (margin_percent / 100.0)), 2
  )


def clear_user_state(user_id):
  if user_id in user_order_state:
    del user_order_state[user_id]


# ==================== KEYBOARDS ====================
def main_menu():
  markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
  markup.add(
      types.KeyboardButton("🛍 Select Platform"),
      types.KeyboardButton("💰 My Balance"),
      types.KeyboardButton("📜 My Orders"),
      types.KeyboardButton("💳 Add Funds (QR & UPI)"),
      types.KeyboardButton("📞 Support"),
  )
  return markup


def platforms_inline_menu():
  markup = types.InlineKeyboardMarkup(row_width=2)
  markup.add(
      types.InlineKeyboardButton(
          "👑 IG Followers Only", callback_data="plat_ig_followers"
      )
  )
  markup.add(
      types.InlineKeyboardButton(
          "📸 Instagram All", callback_data="plat_instagram"
      ),
      types.InlineKeyboardButton("✈️ Telegram", callback_data="plat_telegram"),
      types.InlineKeyboardButton("▶️ YouTube", callback_data="plat_youtube"),
      types.InlineKeyboardButton("📘 Facebook", callback_data="plat_facebook"),
      types.InlineKeyboardButton("🐦 Twitter (X)", callback_data="plat_twitter"),
      types.InlineKeyboardButton("💬 WhatsApp", callback_data="plat_whatsapp"),
  )
  return markup


# ==================== HANDLERS ====================
@bot.message_handler(commands=["start"])
def start_handler(message):
  user_id = message.from_user.id
  clear_user_state(user_id)
  register_user(user_id)
  bot.send_message(
      message.chat.id,
      f"✨ **Namaste {message.from_user.first_name}!** ✨\n\nWelcome to Social"
      " Media Services Bot!",
      parse_mode="Markdown",
      reply_markup=main_menu(),
  )


@bot.message_handler(commands=["addfunds"])
def addfunds_command(message):
  ask_amount_logic(message.chat.id, message.from_user.first_name)


# --- Margin Command ---
@bot.message_handler(commands=["setmargin"])
def set_margin_command(message):
  user_id = message.from_user.id
  if user_id == ADMIN_ID:
    try:
      parts = message.text.split()
      if len(parts) < 2:
        bot.reply_to(
            message,
            "❌ Sahi format use karein: `/setmargin 35`",
            parse_mode="Markdown",
        )
        return
      new_margin = float(parts[1])
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "UPDATE settings SET value = %s WHERE key = 'profit_margin'",
          (new_margin,),
      )
      conn.commit()
      cursor.close()
      conn.close()
      bot.reply_to(
          message,
          f"✅ Profit margin successfully updated to **{new_margin}%**",
          parse_mode="Markdown",
      )
    except ValueError:
      bot.reply_to(
          message,
          "❌ Kripya valid number dalein, jaise: `/setmargin 30`",
          parse_mode="Markdown",
      )
  else:
    bot.reply_to(message, "❌ Yeh command sirf Admin use kar sakta hai.")


def ask_amount_logic(chat_id, first_name):
  msg = bot.send_message(
      chat_id,
      "💰 **Kitna amount add karna chahte hain?**\n(Minimum ₹10)",
      parse_mode="Markdown",
  )
  bot.register_next_step_handler(msg, process_payment_amount)


def process_payment_amount(message):
  if message.text in MENU_BUTTONS:
    handle_menu_buttons(message)
    return
  try:
    amount_rs = float(message.text.strip())
    if amount_rs < 10:
      bot.reply_to(message, "❌ Minimum amount ₹10 hai.")
      return
    payment_link = razorpay_client.payment_link.create({
        "amount": int(amount_rs * 100),
        "currency": "INR",
        "description": f"Add ₹{amount_rs} to Wallet",
        "customer": {
            "name": str(message.from_user.first_name),
            "contact": "9876543210",
            "email": "user@example.com",
        },
    })
    bot.reply_to(
        message,
        f"💳 **Payment Link:**\n\n🔗 {payment_link.get('short_url')}",
        parse_mode="Markdown",
    )
  except Exception as e:
    bot.reply_to(message, f"Error: {str(e)}")


@bot.message_handler(func=lambda message: message.text in MENU_BUTTONS)
def handle_menu_buttons(message):
  user_id = message.from_user.id
  text = message.text
  clear_user_state(user_id)
  register_user(user_id)

  if text == "🛍 Select Platform":
    bot.send_message(
        message.chat.id,
        "👇 **Select Platform or Category:**",
        parse_mode="Markdown",
        reply_markup=platforms_inline_menu(),
    )
  elif text == "💰 My Balance":
    bal = get_user(user_id)[0]
    bot.reply_to(
        message,
        f"👤 **User ID:** `{user_id}`\n💰 **Balance:** ₹{bal:.2f}",
        parse_mode="Markdown",
    )
  elif text == "📜 My Orders":
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT order_id, service_name, quantity, cost, date_time FROM orders"
        " WHERE user_id = %s ORDER BY id DESC LIMIT 5",
        (user_id,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    if not rows:
      bot.reply_to(message, "📜 No orders found.")
    else:
      msg = "📜 **Recent Orders:**\n\n" + "".join([
          f"🆔 `{r[0]}` | {r[1]} | Qty: {r[2]} | ₹{r[3]}\n" for r in rows
      ])
      bot.reply_to(message, msg, parse_mode="Markdown")
  elif text == "💳 Add Funds (QR & UPI)":
    text_msg = (
        f"💳 **Add Funds**\n\nUPI ID: `{UPI_ID}`\n\nAap niche diye gaye button par"
        " click karke bhi Razorpay se payment kar sakte hain:"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "💳 Pay via Razorpay", callback_data="pay_razorpay"
        )
    )
    try:
      bot.send_photo(
          message.chat.id,
          photo=QR_CODE_URL,
          caption=text_msg,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except:
      bot.send_message(
          message.chat.id, text_msg, parse_mode="Markdown", reply_markup=markup
      )
  elif text == "📞 Support":
    bot.send_message(message.chat.id, f"🤝 **Support:** {ADMIN_USERNAME}")


@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
  chat_id = call.message.chat.id
  user_id = call.from_user.id

  if call.data == "pay_razorpay":
    bot.answer_callback_query(call.id)
    ask_amount_logic(chat_id, call.from_user.first_name)

  elif call.data.startswith("plat_"):
    platform_name = call.data.replace("plat_", "").lower()
    bot.answer_callback_query(call.id, "Opening Dropdown Menu...")

    title = (
        "Instagram Followers"
        if platform_name == "ig_followers"
        else platform_name.title()
    )

    # Web App Button jo website ki tarah dropdown menu kholega
    markup = types.InlineKeyboardMarkup()
    web_app_url = f"{RENDER_URL}/webapp?platform={platform_name}"
    markup.add(
        types.InlineKeyboardButton(
            "📱 Open Dropdown Menu", web_app=types.WebAppInfo(url=web_app_url)
        )
    )

    bot.send_message(
        chat_id,
        f"📋 **{title} Services:**\n\nNiche diye gaye button par click karke"
        " Dropdown Menu kholen:",
        parse_mode="Markdown",
        reply_markup=markup,
    )


# ==================== FLASK WEBAPP ROUTE (DROPDOWN UI) ====================
@app.route("/webapp")
def webapp():
  platform = request.args.get("platform", "instagram")
  html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SMM Dropdown Menu</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background-color: #18222d; color: #fff; padding: 20px; margin: 0; }
            h2 { text-align: center; color: #2ea6ff; }
            .form-group { margin-bottom: 20px; }
            label { display: block; margin-bottom: 8px; font-weight: bold; font-size: 14px; }
            select, input { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #2b3847; background-color: #212f3d; color: #fff; font-size: 16px; box-sizing: border-box; }
            .btn { width: 100%; background-color: #2ea6ff; color: white; border: none; padding: 14px; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 10px; }
            .btn:active { background-color: #1a8ad4; }
        </style>
    </head>
    <body>
        <h2>⚡ SMM Dropdown Menu</h2>
        <div class="form-group">
            <label>Select Service Category / Item:</label>
            <select id="serviceSelect">
                <option value="">Loading services...</option>
            </select>
        </div>
        <div class="form-group">
            <label>Link:</label>
            <input type="text" id="orderLink" placeholder="Enter your link here...">
        </div>
        <div class="form-group">
            <label>Quantity:</label>
            <input type="number" id="orderQty" placeholder="Enter quantity...">
        </div>
        <button class="btn" onclick="submitOrder()">Submit Order</button>

        <script>
            let tg = window.Telegram.WebApp;
            tg.expand();

            async function loadServices() {
                try {
                    let response = await fetch('https://smmwiz.com/api/v2', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: 'key={{ api_key }}&action=services'
                    });
                    let data = await response.json();
                    let select = document.getElementById('serviceSelect');
                    select.innerHTML = '<option value="">-- Choose Service --</option>';
                    
                    let plat = "{{ platform }}";
                    data.forEach(s => {
                        let cat = s.category ? s.category.toLowerCase() : '';
                        let name = s.name ? s.name.toLowerCase() : '';
                        let match = false;
                        if(plat === 'ig_followers') {
                            if((cat.includes('instagram') || name.includes('instagram') || cat.includes('ig') || name.includes('ig')) && (cat.includes('follower') || name.includes('follower'))) match = true;
                        } else {
                            if(cat.includes(plat) || name.includes(plat)) match = true;
                        }
                        if(match) {
                            let opt = document.createElement('option');
                            opt.value = s.service;
                            opt.text = s.name + " - Rate: " + s.rate;
                            select.appendChild(opt);
                        }
                    });
                } catch(e) {
                    document.getElementById('serviceSelect').innerHTML = '<option>Error loading services</option>';
                }
            }
            loadServices();

            function submitOrder() {
                let service = document.getElementById('serviceSelect').value;
                let link = document.getElementById('orderLink').value;
                let qty = document.getElementById('orderQty').value;
                if(!service || !link || !qty) {
                    alert('Please fill all fields!');
                    return;
                }
                tg.sendData(JSON.stringify({service: service, link: link, quantity: qty}));
                tg.close();
            }
        </script>
    </body>
    </html>
    """
  return render_template_string(
      html_template, platform=platform, api_key=SMM_API_KEY
  )


# ==================== FLASK WEBHOOK ROUTE ====================
@app.route("/")
def home():
  return "Bot is running via Webhook!"


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
  if request.headers.get("content-type") == "application/json":
    json_string = request.get_data().decode("utf-8")
    update = types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200
  else:
    return "Forbidden", 403


if __name__ == "__main__":
  bot.remove_webhook()
  bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)
