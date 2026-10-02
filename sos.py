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
    "https://cdn.phototourl.com/member/2026-09-29-6a461151-8c48-4048-9f68-b67201cd71ef.jpg"
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
    "🎁 Refer & Earn",
    "🎁 Claim Free Trial",
    "♻️ Request Refill",
    "🤖 AI Caption Generator",
    "🔑 Reseller API",
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
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT DEFAULT"
        " 0"
    )
    cursor.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER DEFAULT 0"
    )
    cursor.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS has_claimed_trial BOOLEAN"
        " DEFAULT FALSE"
    )
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key TEXT")

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value REAL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS orders (id SERIAL PRIMARY KEY, order_id"
        " TEXT, user_id BIGINT, service_name TEXT, link TEXT, quantity INTEGER,"
        " cost REAL, date_time TEXT)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS pending_funds (user_id BIGINT PRIMARY KEY,"
        " amount REAL, time TIMESTAMP)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS refills (refill_id SERIAL PRIMARY KEY,"
        " order_id TEXT, user_id BIGINT, status TEXT DEFAULT 'Pending',"
        " requested_at TIMESTAMP DEFAULT NOW())"
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
  cursor.execute(
      "SELECT balance, points, api_key FROM users WHERE user_id = %s",
      (user_id,),
  )
  row = cursor.fetchone()
  cursor.close()
  conn.close()
  return row


def register_user(user_id):
  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO users (user_id, balance, referred_by, points,"
      " has_claimed_trial) VALUES (%s, 0.0, 0, 0, FALSE) ON CONFLICT (user_id)"
      " DO NOTHING",
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
      types.KeyboardButton("🎁 Refer & Earn"),
      types.KeyboardButton("🎁 Claim Free Trial"),
      types.KeyboardButton("♻️ Request Refill"),
      types.KeyboardButton("🤖 AI Caption Generator"),
      types.KeyboardButton("🔑 Reseller API"),
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

  text_parts = message.text.split()
  if len(text_parts) > 1 and text_parts[1].startswith("ref_"):
    try:
      referrer_id = int(text_parts[1].replace("ref_", ""))
      if referrer_id != user_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT referred_by FROM users WHERE user_id = %s", (user_id,)
        )
        row = cursor.fetchone()
        if row and row[0] == 0:
          cursor.execute(
              "UPDATE users SET referred_by = %s WHERE user_id = %s",
              (referrer_id, user_id),
          )
          cursor.execute(
              "SELECT points, balance FROM users WHERE user_id = %s",
              (referrer_id,),
          )
          ref_row = cursor.fetchone()
          if ref_row:
            earned_points = random.randint(30, 70)
            new_points = ref_row[0] + earned_points
            new_balance = ref_row[1]

            if new_points >= 100:
              extra_rupees = (new_points // 100) * 1.5
              new_balance += extra_rupees
              new_points = new_points % 100

            cursor.execute(
                "UPDATE users SET points = %s, balance = %s WHERE user_id = %s",
                (new_points, new_balance, referrer_id),
            )
            conn.commit()

            try:
              bot.send_message(
                  referrer_id,
                  f"🎉 *New Referral!* Aapki link se ek naye user ne join kiya"
                  f" hai, aur aapko mile hain **{earned_points} points**!",
                  parse_mode="Markdown",
              )
            except:
              pass
        cursor.close()
        conn.close()
    except Exception as e:
      print("Referral error:", e)

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


@bot.message_handler(commands=["freetrial"])
def freetrial_command(message):
  user_id = message.from_user.id
  register_user(user_id)
  try:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT has_claimed_trial FROM users WHERE user_id = %s", (user_id,)
    )
    row = cursor.fetchone()
    has_claimed = row[0] if row else False

    if has_claimed:
      bot.reply_to(
          message,
          "❌ Aap pehle hi apna **Free Trial** claim kar chuke hain! Ab aap"
          " `/addfunds` se balance add kar sakte hain.",
          parse_mode="Markdown",
      )
    else:
      free_bonus = round(random.uniform(0.58, 1.50), 2)
      cursor.execute(
          "UPDATE users SET balance = balance + %s, has_claimed_trial = TRUE"
          " WHERE user_id = %s",
          (free_bonus, user_id),
      )
      conn.commit()
      bot.reply_to(
          message,
          "🎉 **Congratulations! Aapka Free Trial successfully claim ho gaya"
          f" hai.**\n\n💰 Aapke wallet mein `₹{free_bonus}` ka bonus add kar"
          " diya gaya hai jisse aap services test kar sakte hain!",
          parse_mode="Markdown",
      )
    cursor.close()
    conn.close()
  except Exception as e:
    bot.reply_to(message, f"⚠ Error: {str(e)}")


def ask_amount_logic(chat_id, user_id, first_name):
  msg = bot.send_message(
      chat_id,
      "💰 **Kitna amount add karna chahte hain?**\n(Minimum ₹10)",
      parse_mode="Markdown",
  )
  bot.register_next_step_handler(msg, process_payment_amount)


def process_payment_amount(message):
  user_id = message.from_user.id

  if message.text and any(btn in message.text for btn in MENU_BUTTONS):
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  try:
    amount_rs = float(message.text.strip())
    if amount_rs < 10:
      bot.reply_to(message, "❌ Minimum amount ₹10 hai.")
      ask_amount_logic(message.chat.id, user_id, message.from_user.first_name)
      return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO pending_funds (user_id, amount, time) VALUES (%s, %s,"
        " NOW()) ON CONFLICT (user_id) DO UPDATE SET amount = EXCLUDED.amount,"
        " time = NOW()",
        (user_id, amount_rs),
    )
    conn.commit()
    cursor.close()
    conn.close()

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
            f"1️⃣ Upar diye gaye QR ya UPI ID par **₹{amount_rs}** transfer"
            " karein.\n"
            "2️⃣ Payment successful hone ke baad **UTR (Transaction ID)** ya"
            " **Screenshot** turant yahin bhej dein.\n\n"
            "⏳ *Wallet mein balance 10 seconds ke andar automatic update kar"
            " diya jayega!*"
        ),
        parse_mode="Markdown",
    )
  except ValueError:
    bot.reply_to(
        message,
        "❌ Kripya sirf valid number dalein (jaise: 50 ya 100).",
        parse_mode="Markdown",
    )
    ask_amount_logic(message.chat.id, user_id, message.from_user.first_name)


# ==================== MENU BUTTONS HANDLER ====================
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
    if bal_row:
      bal = bal_row[0]
      pts = bal_row[1]
    else:
      bal = 0.0
      pts = 0
    bot.reply_to(
        message,
        f"👤 **User ID:** `{user_id}`\n💰 **Balance:** ₹{bal:.2f}\n⭐ **Points:**"
        f" {pts} pts (100 pts = ₹1.5)",
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
      markup = types.InlineKeyboardMarkup()
      for r in rows:
        markup.add(
            types.InlineKeyboardButton(
                f"♻️ Refill ID: {r[0]}", callback_data=f"refillreq_{r[0]}"
            )
        )
      msg = "📜 **Recent Orders & Refill Options:**\n\n" + "".join([
          f"🆔 `{r[0]}` | {r[1]} | Qty: {r[2]} | ₹{r[3]}\n" for r in rows
      ])
      bot.reply_to(message, msg, parse_mode="Markdown", reply_markup=markup)
  elif text == "💳 Add Funds (QR & UPI)":
    ask_amount_logic(
        message.chat.id, message.from_user.id, message.from_user.first_name
    )
  elif text == "🎁 Refer & Earn":
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    ref_text = (
        f"🎁 **Refer & Earn Program** 🎁\n\n"
        f"Apne dosto ko invite karein aur random **30 se 70 points** tak"
        f" jeetein!\n"
        f"Jaise hi aapke **100 points** honge, woh automatically **₹1.5** mein"
        f" convert ho jayenge.\n\n"
        f"🔗 **Aapki Unique Referral Link:**\n`{ref_link}`\n\n"
        f"👇 Is link ko copy karke apne dosto ke sath share karein!"
    )
    bot.reply_to(message, ref_text, parse_mode="Markdown")
  elif text == "🎁 Claim Free Trial":
    freetrial_command(message)
  elif text == "♻️ Request Refill":
    bot.reply_to(
        message,
        "♻️ **Auto-Refill Instructions:**\nApne `/myorders` ya status check"
        " section mein jayenge toh wahan har order ke sath **'Request Refill'"
        " ka button mil jayega, wahan se click karein!",
        parse_mode="Markdown",
    )
  elif text == "🤖 AI Caption Generator":
    user_order_state[user_id] = {"mode": "ai_caption"}
    msg = bot.send_message(
        message.chat.id,
        "🤖 **AI Caption Generator**\nApne post ka topic ya niche likhein"
        " (jaise: _gym motivation_ ya _travel vlog_):",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_ai_caption)
  elif text == "🔑 Reseller API":
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM users WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    apikey = row[0] if row else None

    if not apikey:
      import uuid

      apikey = str(uuid.uuid4()).replace("-", "")
      cursor.execute(
          "UPDATE users SET api_key = %s WHERE user_id = %s", (apikey, user_id)
      )
      conn.commit()
    cursor.close()
    conn.close()

    api_doc = (
        f"🔑 **Smart Reseller API Panel**\n\n"
        f"Aap apne SMM panel ya doosre bots ko is bot ke sath connect kar"
        f" sakte hain:\n\n"
        f"🌐 **API URL:** `{RENDER_URL}/api/v2`\n"
        f"🔑 **Your API Key:** `{apikey}`\n\n"
        "Supported actions: `services`, `add`, `status`"
    )
    bot.reply_to(message, api_doc, parse_mode="Markdown")
  elif text == "📞 Support":
    bot.send_message(message.chat.id, f"🤝 **Support:** {ADMIN_USERNAME}")


# ==================== GLOBAL PAYMENT PROOF CATCHER ====================
@bot.message_handler(
    content_types=["text", "photo"],
    func=lambda message: message.from_user.id != ADMIN_ID,
)
def handle_payment_proof_global(message):
  user_id = message.from_user.id

  if message.text and message.text in MENU_BUTTONS:
    handle_menu_buttons(message)
    return

  conn = get_db_connection()
  cursor = conn.cursor()
  cursor.execute(
      "SELECT amount FROM pending_funds WHERE user_id = %s", (user_id,)
  )
  row = cursor.fetchone()

  if not row:
    cursor.close()
    conn.close()
    return

  amount_rs = row[0]
  cursor.execute("DELETE FROM pending_funds WHERE user_id = %s", (user_id,))
  conn.commit()
  cursor.close()
  conn.close()

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
      f"🔔 **New Fund Request / Payment Proof!**\n\n"
      f"👤 User: {user_name} (`{user_id}`)\n"
      f"🔗 Username: {user_username}\n"
      f"💰 Expected Amount: `₹{amount_rs}`\n\n"
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
    print(f"❌ Admin notification error: {e}")

  clear_user_state(user_id)


# ==================== CALLBACK QUERY LISTENER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
  chat_id = call.message.chat.id
  user_id = call.from_user.id

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
          "❌ Is category mein koi service nahi mili.",
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

    list_text = f"📋 *{platform_name.upper()} SERVICES* (Page {page+1}/{total_pages})\n\n```text\n"
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

    list_text += "```"
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
    except:
      pass

  elif call.data.startswith("srv_"):
    service_id = call.data.replace("srv_", "")
    bot.answer_callback_query(call.id)
    user_order_state[user_id] = {"service_id": service_id}
    msg = bot.send_message(
        chat_id,
        "🔗 **Ab apna Link bhejein:**",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(msg, process_order_link)


def process_order_link(message):
  user_id = message.from_user.id
  if message.text and message.text in MENU_BUTTONS:
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  if (
      user_id not in user_order_state
      or "service_id" not in user_order_state[user_id]
  ):
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
  if message.text and message.text in MENU_BUTTONS:
    clear_user_state(user_id)
    handle_menu_buttons(message)
    return

  if (
      user_id not in user_order_state
      or "service_id" not in user_order_state[user_id]
  ):
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
          f" Balance: ₹{current_balance:.2f}",
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
          f" `{smm_order_id}`\n💰 Cost: `₹{total_cost}`",
          parse_mode="Markdown",
      )
    else:
      error_msg = smm_data.get("error", "Unknown SMM Error")
      bot.reply_to(message, f"❌ **Error:** `{error_msg}`", parse_mode="Markdown")

    clear_user_state(user_id)

  except ValueError:
    bot.reply_to(
        message, "❌ Kripya valid number dalein (jaise: 500 ya 1000)."
    )


# ==================== FLASK APP ====================
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
  app.run("0.0.0.0", port)
