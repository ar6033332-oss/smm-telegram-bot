from datetime import datetime
import json
import os
import random
import threading
import time
from flask import Flask, abort, request
import psycopg2
import requests
import telebot
from telebot import types

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SMM_API_KEY = os.environ.get("SMM_API_KEY")

if not BOT_TOKEN:
  raise ValueError("BOT_TOKEN environment variable is not set!")

RENDER_URL = os.environ.get(
    "RENDER_URL", "https://smm-telegram-bot-w9s6.onrender.com"
)
RENDER_URL = RENDER_URL.strip().rstrip("/")
if not RENDER_URL.startswith("http"):
  RENDER_URL = f"https://{RENDER_URL}"

SMM_API_URL = "https://xmediasmm.in/api/v2"

ADMIN_ID = 6658716591
UPI_ID = "arshad79@ptyes"
QR_CODE_URL = (
    "https://cdn.phototourl.com/free/2026-09-21-dffdef71-44c0-487e-add8-9e00412d2593.jpg"
)
ADMIN_USERNAME = "@Socialpookiehelp"

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
user_order_state = {}

cached_services = []

MENU_BUTTONS = [
    "🛍 Select Platform",
    "🔥 Trending Services",
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
    cursor.execute(
        "INSERT INTO settings (key, value) VALUES ('instagram_views_margin',"
        " 60.0) ON CONFLICT (key) DO NOTHING"
    )
    conn.commit()
    cursor.close()
    conn.close()
  except Exception as e:
    print("Database Init Error:", e)


init_db()


# ==================== DYNAMIC ORDER COUNT LOGIC ====================
DATA_FILE = "bot_stats.json"


def get_updated_count():
  try:
    if os.path.exists(DATA_FILE):
      with open(DATA_FILE, "r") as f:
        data = json.load(f)
    else:
      data = {"count": 70000, "last_updated": str(datetime.now().date())}

    today_str = str(datetime.now().date())

    if data.get("last_updated") != today_str:
      increment = random.randint(300, 700)
      data["count"] += increment
      data["last_updated"] = today_str

      with open(DATA_FILE, "w") as f:
        json.dump(data, f)

    return data.get("count", 70000)
  except Exception as e:
    print("Stats error:", e)
    return 70000


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


def get_instagram_views_margin():
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT value FROM settings WHERE key = 'instagram_views_margin'"
  )
  row = cursor.fetchone()
  cursor.close()
  conn.close()
  return row[0] if row else 60.0


def is_instagram_views_service(service_name, category_name):
  name = (service_name or "").lower()
  cat = (category_name or "").lower()
  if (
      "instagram" in cat
      or "ig" in cat
      or "instagram" in name
      or "ig" in name
  ) and ("view" in name or "view" in cat):
    return True
  return False


def calculate_selling_price(wholesale_rate, service_name="", category_name=""):
  try:
    wholesale_rate = float(wholesale_rate)
  except:
    wholesale_rate = 0.0

  if is_instagram_views_service(service_name, category_name):
    margin_percent = get_instagram_views_margin()
  else:
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
      types.KeyboardButton("🔥 Trending Services"),
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
          "👑 IG Followers Only", callback_data="plat_ig_followers_0"
      )
  )
  markup.add(
      types.InlineKeyboardButton(
          "📸 Instagram All", callback_data="plat_instagram_0"
      ),
      types.InlineKeyboardButton("✈️ Telegram", callback_data="plat_telegram_0"),
      types.InlineKeyboardButton("▶️ YouTube", callback_data="plat_youtube_0"),
      types.InlineKeyboardButton("📘 Facebook", callback_data="plat_facebook_0"),
      types.InlineKeyboardButton(
          "🐦 Twitter (X)", callback_data="plat_twitter_0"
      ),
      types.InlineKeyboardButton("💬 WhatsApp", callback_data="plat_whatsapp_0"),
  )
  return markup


# ==================== HANDLERS ====================
@bot.message_handler(commands=["start"])
def start_handler(message):
  user_id = message.from_user.id
  clear_user_state(user_id)
  register_user(user_id)

  total_orders = get_updated_count()

  bot.send_message(
      message.chat.id,
      f"✨ **Namaste {message.from_user.first_name}!** ✨\n\n"
      f"🚀 Total Successful Orders: **{total_orders:,}+**\n\n"
      "Welcome to Social Media Services Bot!",
      parse_mode="Markdown",
      reply_markup=main_menu(),
  )


@bot.message_handler(commands=["addfunds"])
def addfunds_command(message):
  ask_amount_logic(
      message.chat.id, message.from_user.id, message.from_user.first_name
  )


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
          f"✅ General profit margin successfully updated to **{new_margin}%**",
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


@bot.message_handler(commands=["setigmargin"])
def set_ig_margin_command(message):
  user_id = message.from_user.id
  if user_id == ADMIN_ID:
    try:
      parts = message.text.split()
      if len(parts) < 2:
        bot.reply_to(
            message,
            "❌ Sahi format use karein: `/setigmargin 60`",
            parse_mode="Markdown",
        )
        return
      new_margin = float(parts[1])
      conn = get_db_connection()
      cursor = conn.cursor()
      cursor.execute(
          "UPDATE settings SET value = %s WHERE key = 'instagram_views_margin'",
          (new_margin,),
      )
      conn.commit()
      cursor.close()
      conn.close()
      bot.reply_to(
          message,
          f"✅ Instagram Views profit margin successfully updated to"
          f" **{new_margin}%**",
          parse_mode="Markdown",
      )
    except ValueError:
      bot.reply_to(
          message,
          "❌ Kripya valid number dalein, jaise: `/setigmargin 60`",
          parse_mode="Markdown",
      )
  else:
    bot.reply_to(message, "❌ Yeh command sirf Admin use kar sakta hai.")


@bot.message_handler(commands=["status"])
def status_command(message):
  parts = message.text.split()
  if len(parts) < 2:
    bot.reply_to(
        message,
        "❌ Sahi format use karein: `/status <Order_ID>`\nJaise: `/status"
        " 123456`",
        parse_mode="Markdown",
    )
    return

  order_id = parts[1].strip()
  user_id = message.from_user.id
  check_and_send_status(message.chat.id, user_id, order_id, is_reply=True)


def check_and_send_status(chat_id, user_id, order_id, is_reply=False):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT user_id, cost, service_name FROM orders WHERE order_id = %s",
      (order_id,),
  )
  order_row = cursor.fetchone()
  cursor.close()
  conn.close()

  if not order_row:
    text = "❌ Yeh Order ID database mein nahi mili. Sahi Order ID enter karein."
    if is_reply:
      bot.reply_to(bot.get_chat(chat_id), text, parse_mode="Markdown")
    else:
      bot.send_message(chat_id, text, parse_mode="Markdown")
    return

  db_user_id, order_cost, service_name = order_row

  if user_id != ADMIN_ID and user_id != db_user_id:
    text = "❌ Aap sirf apne orders ka status check kar sakte hain."
    if is_reply:
      bot.reply_to(bot.get_chat(chat_id), text)
    else:
      bot.send_message(chat_id, text)
    return

  try:
    payload = {"key": SMM_API_KEY, "action": "status", "order": order_id}
    response = requests.post(SMM_API_URL, data=payload, timeout=10)
    res_data = response.json()

    if "error" in res_data:
      text = f"❌ **SMM Error:** `{res_data['error']}`"
      if is_reply:
        bot.reply_to(bot.get_chat(chat_id), text, parse_mode="Markdown")
      else:
        bot.send_message(chat_id, text, parse_mode="Markdown")
      return

    status = res_data.get("status", "Unknown")
    remains = res_data.get("remains", "N/A")
    start_count = res_data.get("start_count", "N/A")

    status_msg = (
        f"📊 **Order Status Details**\n\n"
        f"🆔 **Order ID:** `{order_id}`\n"
        f"📦 **Service:** `{service_name}`\n"
        f"📌 **Status:** `{status}`\n"
        f"📉 **Remains:** `{remains}`\n"
        f"📈 **Start Count:** `{start_count}`"
    )

    if status.lower() in ["canceled", "refunded"]:
      update_balance(db_user_id, order_cost)
      status_msg += (
          f"\n\n💰 **Auto-Refunded:** `₹{order_cost}` aapke account mein wapas"
          " jama kar diye gaye hain kyunki order cancel ho gaya tha."
      )

    if is_reply:
      bot.reply_to(bot.get_chat(chat_id), status_msg, parse_mode="Markdown")
    else:
      bot.send_message(chat_id, status_msg, parse_mode="Markdown")

  except Exception as e:
    text = f"❌ Status fetch karne mein error aayi: {str(e)}"
    if is_reply:
      bot.reply_to(bot.get_chat(chat_id), text)
    else:
      bot.send_message(chat_id, text)


@bot.message_handler(commands=["broadcast"])
def broadcast_command(message):
  user_id = message.from_user.id
  if user_id != ADMIN_ID:
    bot.reply_to(message, "❌ Yeh command sirf Admin ke liye hai.")
    return

  text_parts = message.text.split(maxsplit=1)
  if len(text_parts) < 2:
    bot.reply_to(
        message,
        "❌ Sahi format use karein:\n`/broadcast Aapka message yahan likhein`",
        parse_mode="Markdown",
    )
    return

  broadcast_text = text_parts[1]

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute("SELECT user_id FROM users")
  all_users = cursor.fetchall()
  cursor.close()
  conn.close()

  success_count = 0
  fail_count = 0

  bot.reply_to(
      message,
      f"📢 Broadcast shuru ho gaya hai... Total users: {len(all_users)}",
  )

  for row in all_users:
    uid = row[0]
    try:
      bot.send_message(
          uid,
          f"📢 **Announcement:**\n\n{broadcast_text}",
          parse_mode="Markdown",
      )
      success_count += 1
      time.sleep(0.1)
    except Exception:
      fail_count += 1

  bot.send_message(
      message.chat.id,
      f"✅ **Broadcast Completed!**\n\nSuccessful: `{success_count}`\nFailed"
      f" (Blocked/Inactive): `{fail_count}`",
      parse_mode="Markdown",
  )


@bot.message_handler(commands=["addbal"])
def add_balance_admin(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "❌ Yeh command sirf Admin ke liye hai.")
    return
  parts = message.text.split()
  if len(parts) < 3:
    bot.reply_to(
        message,
        "❌ Sahi format: `/addbal <User_ID> <Amount>`\nJaise: `/addbal"
        " 123456789 50`",
        parse_mode="Markdown",
    )
    return
  try:
    target_user_id = int(parts[1])
    amount = float(parts[2])
    register_user(target_user_id)
    update_balance(target_user_id, amount)
    bot.reply_to(
        message,
        f"✅ Success! User `{target_user_id}` ke account mein `₹{amount}` add"
        " kar diye gaye hain.",
        parse_mode="Markdown",
    )
    try:
      bot.send_message(
          target_user_id,
          f"💰 **Balance Updated:** Admin ne aapke wallet mein `₹{amount}` add"
          " kar diye hain!",
          parse_mode="Markdown",
      )
    except:
      pass
  except ValueError:
    bot.reply_to(
        message,
        "❌ Kripya valid User ID aur Amount dalein.",
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["cutbal"])
def cut_balance_admin(message):
  if message.from_user.id != ADMIN_ID:
    bot.reply_to(message, "❌ Yeh command sirf Admin ke liye hai.")
    return
  parts = message.text.split()
  if len(parts) < 3:
    bot.reply_to(
        message,
        "❌ Sahi format: `/cutbal <User_ID> <Amount>`\nJaise: `/cutbal"
        " 123456789 50`",
        parse_mode="Markdown",
    )
    return
  try:
    target_user_id = int(parts[1])
    amount = float(parts[2])
    update_balance(target_user_id, -amount)
    bot.reply_to(
        message,
        f"✅ Success! User `{target_user_id}` ke account سے `₹{amount}` kaat"
        " liye gaye hain.",
        parse_mode="Markdown",
    )
    try:
      bot.send_message(
          target_user_id,
          f"⚠️ **Balance Deducted:** Admin ne aapke wallet se `₹{amount}` kaat"
          " liye hain.",
          parse_mode="Markdown",
      )
    except:
      pass
  except ValueError:
    bot.reply_to(
        message,
        "❌ Kripya valid User ID aur Amount dalein.",
        parse_mode="Markdown",
    )


def ask_amount_logic(chat_id, user_id, first_name):
  user_order_state[user_id] = {"expecting_amount": True}
  msg = bot.send_message(
      chat_id,
      "💰 **Kitna amount add karna chahte hain?**\n(Minimum ₹10)",
      parse_mode="Markdown",
  )
  bot.register_next_step_handler(msg, process_payment_amount)


def process_payment_amount(message):
  user_id = message.from_user.id
  if message.text in MENU_BUTTONS:
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return
  try:
    amount_rs = float(message.text.strip())
    if amount_rs < 10:
      bot.reply_to(message, "❌ Minimum amount ₹10 hai.")
      return

    user_order_state[user_id] = {
        "expecting_utr": True,
        "fund_amount": amount_rs,
    }

    bot.send_photo(
        message.chat.id,
        photo=QR_CODE_URL,
        caption=(
            "🛡 **SECURE ENCRYPTED UPI GATEWAY** 🛡\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ **Status:** Active & Instant Credit\n"
            f"🆔 **UPI ID:** `{UPI_ID}`\n"
            f"💰 **Payable Amount:** `₹{amount_rs}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🚨 **IMPORTANT INSTRUCTIONS:**\n"
            f"1️⃣ Upar diye gaye QR ya UPI ID par **₹{amount_rs}** transfer karein.\n"
            "2️⃣ Payment successful hone ke baad **UTR (Transaction ID)** ya **Screenshot** turant yahin bhej dein.\n\n"
            "⏳ *Wallet mein balance 10 seconds ke andar automatic update kar diya jayega!*"
        ),
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(message, process_payment_proof)

  except Exception as e:
    clear_user_state(user_id)
    bot.reply_to(message, f"Error: {str(e)}")


def process_payment_proof(message):
  user_id = message.from_user.id

  if message.text and message.text in MENU_BUTTONS:
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  state = user_order_state.get(user_id, {})
  amount_rs = state.get("fund_amount", 0)

  if not amount_rs:
    clear_user_state(user_id)
    bot.reply_to(
        message,
        "❌ Session expired ya amount missing. Dobara 'Add Funds' par click"
        " karein.",
    )
    return

  markup = types.InlineKeyboardMarkup(row_width=2)
  markup.add(
      types.InlineKeyboardButton(
          "✅ Approve", callback_data=f"app_{user_id}_{amount_rs}"
      ),
      types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}"),
  )

  user_name = message.from_user.first_name or "User"
  user_username = (
      f"@{message.from_user.username}"
      if message.from_user.username
      else "No Username"
  )

  caption_text = (
      f"🔔 **New Fund Request!**\n\n"
      f"👤 User: {user_name} (`{user_id}`)\n"
      f"🔗 Username: {user_username}\n"
      f"💰 Amount: `₹{amount_rs}`\n\n"
      f"Neeche diye gaye button par click karke balance approve karein:"
  )

  try:
    if message.photo:
      file_id = message.photo[-1].file_id
      bot.send_photo(
          ADMIN_ID,
          photo=file_id,
          caption=caption_text,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    else:
      proof_text = message.text or "No text"
      full_text = f"{caption_text}\n💬 **Proof/UTR:** `{proof_text}`"
      bot.send_message(
          ADMIN_ID, full_text, parse_mode="Markdown", reply_markup=markup
      )

    bot.reply_to(
        message,
        "✅ **Payment Proof Submitted!**\nAdmin ne aapka request check kar liya"
        " hai, jald hi aapke wallet mein balance add ho jayega.",
        parse_mode="Markdown",
    )
  except Exception as e:
    print("Admin notification error:", e)
    bot.reply_to(
        message,
        "❌ Proof bhejne mein kuch error aayi. Kripya Support se contact"
        " karein.",
    )

  clear_user_state(user_id)


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
  elif text == "🔥 Trending Services":
    services = get_cached_smm_services()
    trending_matches = []
    for s in services:
      name = s.get("name", "").lower()
      cat = s.get("category", "").lower()
      if (
          "follower" in name
          or "subscriber" in name
          or "view" in name
          or "like" in name
      ):
        trending_matches.append(s)
        if len(trending_matches) >= 10:
          break

    if not trending_matches:
      bot.reply_to(
          message, "❌ Filhal koi trending services available nahi hain."
      )
      return

    list_text = "🔥 *TOP TRENDING & BEST SERVICES* 🔥\n\n```text\n"
    markup = types.InlineKeyboardMarkup()

    for idx, s in enumerate(trending_matches, start=1):
      s_name = s.get("name", "")
      s_cat = s.get("category", "")
      selling_price = calculate_selling_price(
          s.get("rate", 0), s_name, s_cat
      )
      service_id = str(s.get("service"))

      list_text += f"{idx}. ID:{service_id} | ₹{selling_price}/1K\n   {s_name}\n\n"
      markup.add(
          types.InlineKeyboardButton(
              f"🛒 #{idx} (ID: {service_id})", callback_data=f"srv_{service_id}"
          )
      )

    list_text += "```\n👇 *Service select karne ke liye button dabayein:*"
    bot.send_message(
        message.chat.id,
        list_text,
        parse_mode="Markdown",
        reply_markup=markup,
    )

  elif text == "💰 My Balance":
    bal_row = get_user(user_id)
    bal = bal_row[0] if bal_row else 0.0
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
    ask_amount_logic(
        message.chat.id, message.from_user.id, message.from_user.first_name
    )
  elif text == "📞 Support":
    bot.send_message(message.chat.id, f"🤝 **Support:** {ADMIN_USERNAME}")


@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
  chat_id = call.message.chat.id
  user_id = call.from_user.id

  # 🔍 LIVE STATUS CHECK HANDLER
  if call.data.startswith("chkstatus_"):
    order_id = call.data.replace("chkstatus_", "")
    bot.answer_callback_query(call.id, "Fetching live status...")
    check_and_send_status(chat_id, user_id, order_id, is_reply=False)
    return

  if call.data.startswith("app_") or call.data.startswith("rej_"):
    if user_id != ADMIN_ID:
      bot.answer_callback_query(call.id, "❌ Aap admin nahi hain!", show_alert=True)
      return

    parts = call.data.split("_")
    action = parts[0]
    target_user_id = int(parts[1])

    if action == "app":
      amount = float(parts[2])
      register_user(target_user_id)
      update_balance(target_user_id, amount)

      try:
        bot.edit_message_caption(
            chat_id=chat_id,
            message_id=call.message.message_id,
            caption=(
                f"{call.message.caption}\n\n"
                f"✅ **STATUS: APPROVED** (₹{amount} Added)"
            ),
            parse_mode="Markdown",
            reply_markup=None,
        )
      except:
        try:
          bot.edit_message_text(
              chat_id=chat_id,
              message_id=call.message.message_id,
              text=f"{call.message.text}\n\n✅ **STATUS: APPROVED** (₹{amount} Added)",
              parse_mode="Markdown",
              reply_markup=None,
          )
        except:
          pass

      bot.answer_callback_query(call.id, f"Successfully added ₹{amount}!")

      try:
        bot.send_message(
            target_user_id,
            f"🎉 **Payment Approved!**\nAdmin ne aapka payment verify kar liya"
            f" hai. Aapke wallet mein `₹{amount}` add kar diye gaye hain!",
            parse_mode="Markdown",
        )
      except:
        pass

    elif action == "rej":
      try:
        bot.edit_message_caption(
            chat_id=chat_id,
            message_id=call.message.message_id,
            caption=f"{call.message.caption}\n\n❌ **STATUS: REJECTED**",
            parse_mode="Markdown",
            reply_markup=None,
        )
      except:
        try:
          bot.edit_message_text(
              chat_id=chat_id,
              message_id=call.message.message_id,
              text=f"{call.message.text}\n\n❌ **STATUS: REJECTED**",
              parse_mode="Markdown",
              reply_markup=None,
          )
        except:
          pass

      bot.answer_callback_query(call.id, "Payment rejected!")

      try:
        bot.send_message(
            target_user_id,
            "❌ **Payment Rejected:** Aapka payment proof invalid ya match nahi"
            " hua. Kripya support se contact karein.",
            parse_mode="Markdown",
        )
      except:
        pass
    return

  if call.data.startswith("plat_"):
    bot.answer_callback_query(call.id, "Loading services...")

    parts = call.data.split("_")
    page = int(parts[-1])
    platform_name = "_".join(parts[1:-1])

    services = get_cached_smm_services()
    matched_services = []

    for s in services:
      cat = s.get("category", "").lower()
      name = s.get("name", "").lower()
      match = False

      if platform_name == "ig_followers":
        if (
            "instagram" in cat or "ig" in cat or "instagram" in name
        ) and ("follower" in cat or "followers" in name):
          match = True
      elif platform_name == "instagram":
        if (
            "instagram" in cat or "ig" in cat or "instagram" in name
        ) and not ("follower" in cat or "followers" in name):
          match = True
      elif platform_name == "telegram":
        if "telegram" in cat or "tg" in cat or "telegram" in name:
          match = True
      elif platform_name == "youtube":
        if "youtube" in cat or "yt" in cat or "youtube" in name:
          match = True
      elif platform_name == "facebook":
        if "facebook" in cat or "fb" in cat or "facebook" in name:
          match = True
      elif platform_name == "twitter":
        if (
            "twitter" in cat
            or "x.com" in cat
            or "twitter" in name
            or "x followers" in name
        ):
          match = True
      elif platform_name == "whatsapp":
        if "whatsapp" in cat or "wa" in cat or "whatsapp" in name:
          match = True

      if match:
        matched_services.append(s)

    if not matched_services:
      bot.edit_message_text(
          "❌ Is category mein koi service nahi mili. Kripya dusri category try"
          " karein.",
          chat_id=chat_id,
          message_id=call.message.message_id,
          parse_mode="Markdown",
      )
      return

    ITEMS_PER_PAGE = 5
    total_services = len(matched_services)
    total_pages = (total_services + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page >= total_pages:
      page = total_pages - 1
    if page < 0:
      page = 0

    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_services = matched_services[start_idx:end_idx]

    list_text = f"📋 *{platform_name.upper()} SERVICES LIST* (Page {page+1}/{total_pages}) 📋\n\n```text\n"

    markup = types.InlineKeyboardMarkup()
    buttons = []

    for idx, s in enumerate(current_services, start=start_idx + 1):
      s_name = s.get("name", "")
      s_cat = s.get("category", "")
      selling_price = calculate_selling_price(
          s.get("rate", 0), s_name, s_cat
      )
      service_id = str(s.get("service"))

      list_text += f"{idx}. ID:{service_id} | ₹{selling_price}/1K\n   {s_name}\n\n"

      buttons.append(
          types.InlineKeyboardButton(
              f"🛒 #{idx} (ID: {service_id})", callback_data=f"srv_{service_id}"
          )
      )

    list_text += "```\n👇 *Service select karein ya page badlein:*"

    for btn in buttons:
      markup.add(btn)

    nav_buttons = []
    if page > 0:
      nav_buttons.append(
          types.InlineKeyboardButton(
              "⬅️ Prev", callback_data=f"plat_{platform_name}_{page-1}"
          )
      )
    if page < total_pages - 1:
      nav_buttons.append(
          types.InlineKeyboardButton(
              "Next ➡️", callback_data=f"plat_{platform_name}_{page+1}"
          )
      )

    if nav_buttons:
      markup.row(*nav_buttons)

    try:
      bot.edit_message_text(
          list_text,
          chat_id=chat_id,
          message_id=call.message.message_id,
          parse_mode="Markdown",
          reply_markup=markup,
      )
    except Exception:
      bot.send_message(
          chat_id,
          list_text,
          parse_mode="Markdown",
          reply_markup=markup,
      )

  elif call.data.startswith("srv_"):
    service_id = call.data.replace("srv_", "")
    bot.answer_callback_query(call.id)
    user_order_state[user_id] = {"service_id": service_id}

    msg = bot.send_message(
        chat_id,
        "🔗 **Ab apna Link bhejein** (jahan followers/likes/views chahiye):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_order_link)


def process_order_link(message):
  user_id = message.from_user.id
  if message.text in MENU_BUTTONS:
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  if user_id not in user_order_state or "service_id" not in user_order_state[user_id]:
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
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  if user_id not in user_order_state or "service_id" not in user_order_state[user_id]:
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
    s_name = selected_service.get("name", "")
    s_cat = selected_service.get("category", "")
    unit_selling_price = calculate_selling_price(
        wholesale_rate, s_name, s_cat
    )
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

      # 🔍 ORDER SUCCESS KE SAATH LIVE STATUS BUTTON ADD KIYA GAYA HAI
      markup = types.InlineKeyboardMarkup()
      markup.add(
          types.InlineKeyboardButton(
              "🔍 Check Live Status", callback_data=f"chkstatus_{smm_order_id}"
          )
      )

      bot.reply_to(
          message,
          f"✅ **Order Placed Successfully!**\n\n🆔 Order ID:"
          f" `{smm_order_id}`\n📦 Service:"
          f" `{selected_service.get('name')}`\n🔗 Link: `{link}`\n📊 Quantity:"
          f" `{quantity}`\n💰 Cost: `₹{total_cost}`\n📉 Remaining Balance:"
          f" `₹{current_balance - total_cost:.2f}`",
          parse_mode="Markdown",
          reply_markup=markup,
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


# ==================== FLASK WEBHOOK ROUTES ====================
@app.route("/")
def home():
  return "Bot is running via Webhook!"


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
  if request.headers.get("content-type") == "application/json":
    json_string = request.get_data().decode("utf-8")
    update = types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200
  else:
    return "Forbidden", 403


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
