from datetime import datetime
import json
import os
import threading
import time
from flask import Flask, request
import psycopg2
import razorpay
import requests
import telebot
from telebot import types

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8203717604:AAEXt0oAR7FDbSoQ4pBZTZxXEQwJp6WyMOc"
RENDER_URL = "[https://smm-telegram-bot-w9s6.onrender.com](https://smm-telegram-bot-w9s6.onrender.com)"

# XMedia SMM API Details
SMM_API_URL = "https://xmediasmm.in/api/v2"
SMM_API_KEY = "08a1a294cbd54b19bdb1e5cf3c2682dc"

ADMIN_ID = 6658716591
UPI_ID = "arshad79@ptyes"
QR_CODE_URL = (
    "[https://cdn.phototourl.com/free/2026-09-21-dffdef71-44c0-487e-add8-9e00412d2593.jpg](https://cdn.phototourl.com/free/2026-09-21-dffdef71-44c0-487e-add8-9e00412d2593.jpg)"
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

cached_services = []

MENU_BUTTONS = [
    "🛍 Select Platform",
    "💰 My Balance",
    "📜 My Orders",
    "💳 Add Funds (QR & UPI)",
    "📞 Support",
]

# ==================== DATABASE SETUP ====================
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
  if DATABASE_URL:
    return psycopg2.connect(DATABASE_URL)
  else:
    raise ValueError("DATABASE_URL environment variable is not set!")


def init_db():
  try:
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
        "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, order_id"
        " TEXT, user_id BIGINT, service_name TEXT, link TEXT, quantity INTEGER,"
        " cost REAL, date_time TEXT)"
    )
    cursor.execute(
        "INSERT INTO settings (key, value) VALUES ('profit_margin', 40.0) ON"
        " CONFLICT (key) DO NOTHING"
    )
    conn.commit()
    cursor.close()
    conn.close()
  except Exception as e:
    print("Database Init Error:", e)


init_db()


# ==================== BACKGROUND SERVICE FETCHER ====================
def fetch_services_background():
  global cached_services
  while True:
    try:
      response = requests.post(
          SMM_API_URL,
          data={"key": SMM_API_KEY, "action": "services"},
          timeout=15,
      )
      if response.status_code == 200:
        res_data = response.json()
        if isinstance(res_data, list) and len(res_data) > 0:
          cached_services = res_data
    except Exception as e:
      print("Background fetch error:", e)
    time.sleep(300)


def get_cached_smm_services():
  global cached_services
  if not cached_services:
    try:
      response = requests.post(
          SMM_API_URL, data={"key": SMM_API_KEY, "action": "services"}, timeout=5
      )
      if response.status_code == 200:
        res_data = response.json()
        if isinstance(res_data, list):
          cached_services = res_data
    except:
      pass
  return cached_services


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
  try:
    wholesale_rate = float(wholesale_rate)
  except:
    wholesale_rate = 0.0
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
    bot.answer_callback_query(call.id, "Loading services...")

    services = get_cached_smm_services()
    matched_services = []

    for s in services:
      cat = s.get("category", "").lower()
      name = s.get("name", "").lower()
      match = False

      if platform_name == "ig_followers":
        if (
            "instagram" in cat
            or "ig" in cat
            or "instagram" in name
            or "ig" in name
        ) and ("follower" in cat or "follower" in name):
          match = True
      else:
        if platform_name in cat or platform_name in name:
          match = True

      if match:
        matched_services.append(s)

    if not matched_services:
      bot.send_message(
          chat_id,
          "❌ Is category mein koi service nahi mili.",
          parse_mode="Markdown",
      )
      return

    # Ek hi code block me saari services aur poore naam dikhane ke liye format
    list_text = f"📋 *{platform_name.upper()} SERVICES LIST* 📋\n\n```text\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []

    for i, s in enumerate(matched_services[:8], 1):
      selling_price = calculate_selling_price(s.get("rate", 0))
      full_name = s.get("name")
      service_id = str(s.get("service"))

      # Code block ke andar poora naam aur rate clean format me aayega
      list_text += f"{i}. ID:{service_id} | ₹{selling_price}/1K\n   {full_name}\n\n"

      # Buttons bilkul chote aur clean rakhe gaye hain taaki text na kate
      buttons.append(
          types.InlineKeyboardButton(
              f"🛒 #{i} (ID: {service_id})", callback_data=f"srv_{service_id}"
          )
      )

    list_text += "```\n👇 *Niche diye gaye button se apni service chunein:*"

    for i in range(0, len(buttons), 2):
      if i + 1 < len(buttons):
        markup.add(buttons[i], buttons[i + 1])
      else:
        markup.add(buttons[i])

    bot.send_message(
        chat_id, list_text, parse_mode="Markdown", reply_markup=markup
    )

  elif call.data.startswith("srv_"):
    service_id = call.data.replace("srv_", "")
    bot.answer_callback_query(call.id)
    user_order_state[user_id] = {"service_id": service_id}

    msg = bot.send_message(
        chat_id,
        "🔗 **Ab apna Link bhejein** (jahan followers/likes chahiye):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_order_link)


def process_order_link(message):
  user_id = message.from_user.id
  if message.text in MENU_BUTTONS:
    handle_menu_buttons(message)
    return

  if user_id not in user_order_state:
    bot.reply_to(message, "❌ Session expired. Dobara start karein.")
    return

  user_order_state[user_id]["link"] = message.text.strip()
  msg = bot.send_message(
      message.chat.id,
      "📊 **Quantity kitni chahiye?** (Number me likhein, jaise: 1000)",
      parse_mode="Markdown",
  )
  bot.register_next_step_handler(msg, process_order_quantity)


def process_order_quantity(message):
  user_id = message.from_user.id
  if message.text in MENU_BUTTONS:
    handle_menu_buttons(message)
    return

  if user_id not in user_order_state:
    bot.reply_to(message, "❌ Session expired. Dobara start karein.")
    return

  try:
    quantity = int(message.text.strip())
    if quantity <= 0:
      bot.reply_to(message, "❌ Quantity 0 se zyada honi chahiye.")
      return

    state = user_order_state[user_id]
    service_id = state["service_id"]
    link = state["link"]

    services = get_cached_smm_services()
    selected_service = None
    for s in services:
      if str(s.get("service")) == str(service_id):
        selected_service = s
        break

    if not selected_service:
      bot.reply_to(message, "❌ Selected service not found.")
      clear_user_state(user_id)
      return

    wholesale_rate = float(selected_service.get("rate", 0))
    unit_selling_price = calculate_selling_price(wholesale_rate)
    total_cost = round((unit_selling_price * quantity) / 1000.0, 2)

    user_row = get_user(user_id)
    current_balance = user_row[0] if user_row else 0.0

    if current_balance < total_cost:
      bot.reply_to(
          message,
          f"❌ **Insufficient Balance!**\nRequired: ₹{total_cost}\nYour"
          f" Balance: ₹{current_balance:.2f}\n\nPehle Funds Add karein.",
          parse_mode="Markdown",
      )
      clear_user_state(user_id)
      return

    smm_payload = {
        "key": SMM_API_KEY,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity,
    }
    smm_resp = requests.post(SMM_API_URL, data=smm_payload, timeout=10)
    smm_data = smm_resp.json()

    if "order" in smm_data:
      smm_order_id = str(smm_data["order"])
      update_balance(user_id, -total_cost)

      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO orders (order_id, user_id, service_name, link, quantity,"
          " cost, date_time) VALUES (%s, %s, %s, %s, %s, %s, %s)",
          (
              smm_order_id,
              user_id,
              selected_service.get("name"),
              link,
              quantity,
              total_cost,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          ),
      )
      conn.commit()
      cursor.close()
      conn.close()

      bot.reply_to(
          message,
          f"✅ **Order Placed Successfully!**\n\n🆔 Order ID:"
          f" `{smm_order_id}`\n📦 Service:"
          f" `{selected_service.get('name')}`\n🔗 Link: `{link}`\n📊 Quantity:"
          f" `{quantity}`\n💰 Cost: `₹{total_cost}`\n📉 Remaining Balance:"
          f" `₹{current_balance - total_cost:.2f}`",
          parse_mode="Markdown",
      )
    else:
      error_msg = smm_data.get("error", "Unknown SMM Error")
      bot.reply_to(
          message,
          f"❌ **SMM Panel Error:**\n`{error_msg}`",
          parse_mode="Markdown",
      )

    clear_user_state(user_id)

  except ValueError:
    bot.reply_to(
        message, "❌ Kripya valid number dalein (jaise: 500 ya 1000)."
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


# Background Keep-Alive Ping
def keep_alive():
  while True:
    try:
      requests.get(RENDER_URL, timeout=5)
    except:
      pass
    time.sleep(300)


if __name__ == "__main__":
  threading.Thread(target=fetch_services_background, daemon=True).start()
  threading.Thread(target=keep_alive, daemon=True).start()

  bot.remove_webhook()
  bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)
