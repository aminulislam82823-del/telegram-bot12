import asyncio
import re
import aiosqlite
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from flask import Flask, request
import os
import threading

# ================= কনফিগারেশন =================
# আপনার নতুন বটের টোকেন এবং অ্যাডমিন আইডি
BOT_TOKEN = "8946386467:AAEg9cmo1enXr1bVb8fjWhF6pVoOSJyCG3o"
ADMIN_ID = 8380777485
# ============================================

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

# --- TAMA API Webhook (এই লিংকে TAMA ওটিপি পাঠাবে) ---
@app.route('/tama-webhook', methods=['POST', 'GET'])
def tama_webhook():
    if request.method == 'POST':
        data = request.json
        print("TAMA API থেকে ডেটা এসেছে:", data)
        return "Webhook Received!", 200
    else:
        return "TAMA API Webhook is Running!", 200

@app.route("/")
def webhook():
    return "Bot Web Server is running perfectly on Render!", 200

# FSM States
class AdminStates(StatesGroup):
    waiting_api_key = State()
    waiting_api_url = State()
    waiting_support_user = State()
    waiting_channel_id = State()
    waiting_group_link = State()
    waiting_yt_link = State()
    waiting_min_withdraw = State()
    waiting_withdraw_methods = State()
    
    waiting_new_service_name = State()
    waiting_new_service_code = State()
    
    waiting_rate_service = State()
    waiting_rate_cname = State()
    waiting_rate_ccode = State()
    waiting_rate_dial = State()
    waiting_rate_amount = State()
    waiting_rate_traffic = State()
    
    waiting_delete_rate_id = State()
    
    waiting_num_service = State()
    waiting_num_country = State()
    waiting_numbers_input = State()
    
    waiting_otp_number = State()
    waiting_otp_code = State()

class WithdrawStates(StatesGroup):
    waiting_account = State()
    waiting_amount = State()

def parse_methods(text: str):
    if not text:
        return ["bKash", "Nagad"]
    if any(c in text for c in [",", "/", "|", "\n"]):
        parts = re.split(r'[,/|\n]+', text)
    else:
        parts = text.split()
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned if cleaned else ["bKash", "Nagad"]

async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, api_code TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS rates (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, country_name TEXT, country_code TEXT, dial_code TEXT, rate REAL, traffic TEXT DEFAULT '🟢 High Traffic')''')
        await db.execute('''CREATE TABLE IF NOT EXISTS numbers (id INTEGER PRIMARY KEY AUTOINCREMENT, service TEXT, country_code TEXT, phone_number TEXT UNIQUE, activation_id TEXT DEFAULT NULL, assigned_to INTEGER DEFAULT NULL, status TEXT DEFAULT 'AVAILABLE')''')
        await db.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, total_refers INTEGER DEFAULT 0, daily_otps INTEGER DEFAULT 0, daily_income REAL DEFAULT 0.0, total_otps INTEGER DEFAULT 0, total_income REAL DEFAULT 0.0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT, account TEXT, amount REAL, status TEXT DEFAULT 'PENDING')''')

        default_settings = [
            ("sms_api_key", ""),
            ("sms_api_url", "https://api.sms-activate.org/stubs/handler_api.php"),
            ("api_mode", "AUTO"),
            ("support_username", "@YourSupportUser"),
            ("otp_channel_id", ""),
            ("otp_group_link", "https://t.me/"),
            ("youtube_link", "https://youtube.com/"),
            ("min_withdraw", "50"),
            ("withdraw_methods", "bKash, Nagad, Rocket")
        ]
        for key, val in default_settings:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
        
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] else ""

async def set_setting(key: str, value: str):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

user_cc_mode = {}

def get_main_menu(is_admin: bool = False):
    keyboard = [
        [KeyboardButton(text="📱 GET NUMBER"), KeyboardButton(text="📊 COUNTRYS")],
        [KeyboardButton(text="👑 LEADERBOARD"), KeyboardButton(text="👤 PROFILE")],
        [KeyboardButton(text="📅 WITHDRAWAL"), KeyboardButton(text="👥 SUPPORT")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    
    bot_info = await bot.get_me()
    bot_title = bot_info.first_name or "বট"
    
    is_admin = (message.from_user.id == ADMIN_ID)
    await message.answer(
        f"👋 <b>স্বাগতম {bot_title} এ!</b>\n\nনিচের মেনু থেকে আপনার প্রয়োজনীয় অপশন নির্বাচন করুন:",
        reply_markup=get_main_menu(is_admin)
    )

# --- Server thread ---
def run_web():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

async def main():
    await init_db()
    print("🚀 Bot is running with Admin Panel and Webhook server...")
    
    # Start the Flask web server in a separate thread
    web_thread = threading.Thread(target=run_web)
    web_thread.start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())