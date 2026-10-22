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
    
    # সার্ভিস যোগ
    waiting_new_service_name = State()
    waiting_new_service_code = State()
    
    # দেশ, রেট ও ট্রাফিক যোগ
    waiting_rate_service = State()
    waiting_rate_cname = State()
    waiting_rate_ccode = State()
    waiting_rate_dial = State()
    waiting_rate_amount = State()
    waiting_rate_traffic = State()
    
    # রেট ডিলিট
    waiting_delete_rate_id = State()
    
    # ম্যানুয়াল নম্বর আপলোড
    waiting_num_service = State()
    waiting_num_country = State()
    waiting_numbers_input = State()
    
    # ম্যানুয়াল ওটিপি সেন্ড
    waiting_otp_number = State()
    waiting_otp_code = State()

class WithdrawStates(StatesGroup):
    waiting_account = State()
    waiting_amount = State()

# মেথড পার্স করার শক্তিশালী হেল্পার (কমা, স্ল্যাশ, স্পেস বা নতুন লাইন যাই হোক না কেন আলাদা বাটন হবে)
def parse_methods(text: str):
    if not text:
        return ["bKash", "Nagad"]
    if any(c in text for c in [",", "/", "|", "\n"]):
        parts = re.split(r'[,/|\n]+', text)
    else:
        parts = text.split()
    cleaned = [p.strip() for p in parts if p.strip()]
    return cleaned if cleaned else ["bKash", "Nagad"]

# --- ডাটাবেজ তৈরি ---
async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                api_code TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT,
                country_name TEXT,
                country_code TEXT,
                dial_code TEXT,
                rate REAL,
                traffic TEXT DEFAULT '🟢 High Traffic'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT,
                country_code TEXT,
                phone_number TEXT UNIQUE,
                activation_id TEXT DEFAULT NULL,
                assigned_to INTEGER DEFAULT NULL,
                status TEXT DEFAULT 'AVAILABLE'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                total_refers INTEGER DEFAULT 0,
                daily_otps INTEGER DEFAULT 0,
                daily_income REAL DEFAULT 0.0,
                total_otps INTEGER DEFAULT 0,
                total_income REAL DEFAULT 0.0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                method TEXT,
                account TEXT,
                amount REAL,
                status TEXT DEFAULT 'PENDING'
            )
        ''')

        # ডিফল্ট সেটিংস
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

# --- মূল হোম মেনু ---
def get_main_menu(is_admin: bool = False):
    keyboard = [
        [KeyboardButton(text="📱 GET NUMBER"), KeyboardButton(text="📊 COUNTRYS")],
        [KeyboardButton(text="👑 LEADERBOARD"), KeyboardButton(text="👤 PROFILE")],
        [KeyboardButton(text="📅 WITHDRAWAL"), KeyboardButton(text="👥 SUPPORT")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 ADMIN PANEL")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# --- ইউজার কমান্ড: /start ---
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

# --- ইউজার বাটন: 📱 GET NUMBER ---
@dp.message(F.text.in_(["📱 GET NUMBER", "GET NUMBER"]))
async def show_services(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT name FROM services") as cur:
            services = await cur.fetchall()

    if not services:
        await message.answer("📍 <b>Select a service:</b>\n\n⚠️ বর্তমানে কোনো সার্ভিস যোগ করা নেই। অ্যাডমিন প্যানেল (🛠 ADMIN PANEL) থেকে সার্ভিস যোগ করুন।")
        return

    buttons = []
    for srv in services:
        name = srv[0]
        icon = "✈️" if "TELEGRAM" in name.upper() else ("🎵" if "TIKTOK" in name.upper() else ("📘" if "FACEBOOK" in name.upper() else "🛡"))
        buttons.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"srv_{name}")])
    buttons.append([InlineKeyboardButton(text="❌ Close", callback_data="close_box")])

    await message.answer("📍 <b>Select a service:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# --- সার্ভিস সিলেক্ট করলে দেশ ও ট্রাফিক ---
@dp.callback_query(F.data.startswith("srv_"))
async def select_service(callback: types.CallbackQuery):
    service = callback.data.split("_")[1]
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT country_code, country_name, rate, traffic FROM rates WHERE service = ?", (service,)) as cur:
            countries = await cur.fetchall()

    if not countries:
        await callback.answer(f"{service} সার্ভিসে কোনো দেশ বা রেট এখনো যোগ করা হয়নি! অ্যাডমিন প্যানেলে গিয়ে '🌍 দেশ, রেট ও ট্রাফিক' এ যোগ করুন।", show_alert=True)
        return

    buttons = []
    for c_code, c_name, rate, traffic in countries:
        btn_text = f"🌐 {c_name} - {rate} TK/OTP ({traffic})"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy_{service}_{c_code}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_services")])

    await callback.message.edit_text(f"📍 <b>Select a country for {service}:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "back_services")
async def back_services(callback: types.CallbackQuery):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT name FROM services") as cur:
            services = await cur.fetchall()
    buttons = []
    for srv in services:
        name = srv[0]
        icon = "✈️" if "TELEGRAM" in name.upper() else ("🎵" if "TIKTOK" in name.upper() else ("📘" if "FACEBOOK" in name.upper() else "🛡"))
        buttons.append([InlineKeyboardButton(text=f"{icon} {name}", callback_data=f"srv_{name}")])
    buttons.append([InlineKeyboardButton(text="❌ Close", callback_data="close_box")])
    await callback.message.edit_text("📍 <b>Select a service:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# --- নম্বর দেওয়া (অটো API অথবা ম্যানুয়াল DB) ---
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_number(callback: types.CallbackQuery):
    _, service, country_code = callback.data.split("_")
    user_id = callback.from_user.id
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT country_name, dial_code, rate, traffic FROM rates WHERE service = ? AND country_code = ?", (service, country_code)) as cur:
            rate_info = await cur.fetchone()

        if not rate_info:
            await callback.answer("রেট পাওয়া যায়নি!", show_alert=True)
            return

        c_name, dial_code, rate, traffic = rate_info

    api_key = await get_setting("sms_api_key")
    api_url = await get_setting("sms_api_url")
    api_mode = await get_setting("api_mode")

    phone_number = None
    activation_id = None

    if api_mode == "AUTO" and api_key and api_url:
        async with aiosqlite.connect("database.db") as db:
            async with db.execute("SELECT api_code FROM services WHERE name = ?", (service,)) as cur:
                srv_row = await cur.fetchone()
                srv_api_code = srv_row[0] if srv_row and srv_row[0] else "tg"

        try:
            params = {
                "api_key": api_key,
                "action": "getNumber",
                "service": srv_api_code,
                "country": country_code.lower()
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    resp_text = await resp.text()

            if "ACCESS_NUMBER" in resp_text:
                parts = resp_text.split(":")
                activation_id = parts[1]
                phone_number = parts[2]
                if not phone_number.startswith("+"):
                    phone_number = "+" + phone_number

                async with aiosqlite.connect("database.db") as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO numbers (service, country_code, phone_number, activation_id, assigned_to, status) VALUES (?, ?, ?, ?, ?, 'ACTIVE')",
                        (service, country_code, phone_number, activation_id, user_id)
                    )
                    await db.commit()

                asyncio.create_task(poll_sms_api_otp(user_id, phone_number, activation_id, service, country_code, rate))
        except Exception as e:
            print(f"API Error: {e}")

    if not phone_number:
        async with aiosqlite.connect("database.db") as db:
            async with db.execute(
                "SELECT id, phone_number FROM numbers WHERE service = ? AND country_code = ? AND status = 'AVAILABLE' LIMIT 1",
                (service, country_code)
            ) as n_cur:
                row = await n_cur.fetchone()
                if row:
                    nid, phone_number = row
                    await db.execute("UPDATE numbers SET assigned_to = ?, status = 'ASSIGNED' WHERE id = ?", (user_id, nid))
                    await db.commit()

    if not phone_number:
        await callback.answer("⚠️ এই দেশের কোনো নম্বর বর্তমানে খালি নেই! অ্যাডমিন প্যানেল থেকে নম্বর যুক্ত করুন।", show_alert=True)
        return

    otp_group_link = await get_setting("otp_group_link") or "https://t.me/"
    show_cc = user_cc_mode.get(user_id, True)
    display_num = phone_number if show_cc else phone_number.replace(dial_code, "")
    cc_btn_text = "🗑 Remove CC" if show_cc else "➕ Add CC"

    num_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✈️ 📋 {display_num}", callback_data=f"copy_{phone_number}")],
        [
            InlineKeyboardButton(text="🌐 Country", callback_data=f"srv_{service}"),
            InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh_{service}_{country_code}")
        ],
        [InlineKeyboardButton(text=cc_btn_text, callback_data=f"toggle_cc_{service}_{country_code}")],
        [InlineKeyboardButton(text="🛡 OTP Group", url=otp_group_link)]
    ])

    await callback.message.edit_text(
        f"{service} | 🌐 {c_name}\n"
        f"🚦 <b>Traffic: {traffic}</b>\n"
        f"👝 <b>Price: {rate:.4f} ৳ / OTP</b>",
        reply_markup=num_kb
    )

# --- ওটিপি পোলিং ---
async def poll_sms_api_otp(user_id: int, phone_number: str, activation_id: str, service: str, country_code: str, rate: float):
    api_key = await get_setting("sms_api_key")
    api_url = await get_setting("sms_api_url")
    
    for _ in range(180):
        await asyncio.sleep(5)
        try:
            params = {"api_key": api_key, "action": "getStatus", "id": activation_id}
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    res = await resp.text()

            if "STATUS_OK" in res:
                otp_code = res.split(":")[1].strip()
                await deliver_otp_success(user_id, phone_number, otp_code, country_code, rate)
                try:
                    set_params = {"api_key": api_key, "action": "setStatus", "status": "6", "id": activation_id}
                    async with aiohttp.ClientSession() as session:
                        await session.get(api_url, params=set_params)
                except Exception:
                    pass
                break
            elif "STATUS_CANCEL" in res:
                break
        except Exception as e:
            print(f"Polling error: {e}")

# --- ওটিপি সেন্ড ফাংশন ---
async def deliver_otp_success(user_id: int, phone_number: str, otp_code: str, country_code: str, rate: float):
    async with aiosqlite.connect("database.db") as db:
        await db.execute('''
            UPDATE users SET 
                balance = balance + ?,
                daily_otps = daily_otps + 1,
                daily_income = daily_income + ?,
                total_otps = total_otps + 1,
                total_income = total_income + ?
            WHERE user_id = ?
        ''', (rate, rate, rate, user_id))
        await db.execute("UPDATE numbers SET status = 'COMPLETED' WHERE phone_number = ?", (phone_number,))
        await db.commit()

    user_otp_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🛡 📋 {otp_code}", callback_data="noop")],
        [InlineKeyboardButton(text=f"🎁 Added {rate:.2f} tk", callback_data="noop")]
    ])
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🌐 {country_code} | ✈️ <code>{phone_number}</code> | 💬 English",
            reply_markup=user_otp_kb
        )
    except Exception as e:
        print(f"User inbox error: {e}")

    channel_id = await get_setting("otp_channel_id")
    group_link = await get_setting("otp_group_link") or "https://t.me/"
    yt_link = await get_setting("youtube_link") or "https://youtube.com/"
    masked_number = phone_number[:6] + "XXX" + phone_number[-2:] if len(phone_number) > 8 else phone_number

    bot_info = await bot.get_me()
    bot_title = bot_info.first_name or "OTP MASTER"

    channel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔒 📋 {otp_code}", callback_data="noop")],
        [InlineKeyboardButton(text="🔎 GET SAME NUMBER", callback_data="noop")],
        [
            InlineKeyboardButton(text="🌌 NUMBER", callback_data="noop"),
            InlineKeyboardButton(text="🌆 CHANNEL", url=group_link)
        ],
        [InlineKeyboardButton(text="🎬 YouTube", url=yt_link)]
    ])

    if channel_id:
        try:
            await bot.send_message(
                chat_id=channel_id,
                text=(
                    f"⚜️ <b>{bot_title} OTP</b>\n"
                    f"🌐 {country_code} | ✈️ <code>{masked_number}</code> | English\n\n"
                    f"Telegram code: <b>{otp_code}</b>\n\n"
                    f"You can also tap on this link to confirm your new number:\n"
                    f"https://t.me/login/{otp_code}"
                ),
                reply_markup=channel_kb
            )
        except Exception as e:
            print(f"চ্যানেলে মেসেজ যায়নি: {e}")

@dp.callback_query(F.data.startswith("toggle_cc_"))
async def toggle_country_code(callback: types.CallbackQuery):
    _, _, service, country_code = callback.data.split("_")
    user_id = callback.from_user.id
    current_state = user_cc_mode.get(user_id, True)
    user_cc_mode[user_id] = not current_state
    await process_buy_number(callback)

@dp.callback_query(F.data.startswith("refresh_"))
async def refresh_numbers(callback: types.CallbackQuery):
    _, service, country_code = callback.data.split("_")
    await process_buy_number(callback)

@dp.callback_query(F.data.startswith("copy_"))
async def copy_number_alert(callback: types.CallbackQuery):
    num = callback.data.split("_")[1]
    await callback.answer(f"কপি হয়েছে: {num}", show_alert=False)

# --- ইউজার বাটন: 📊 COUNTRYS (১০০% নির্ভরযোগ্য রেট ও ট্রাফিক লিস্ট) ---
@dp.message(F.text.in_(["📊 COUNTRYS", "COUNTRYS"]))
async def show_countries_list(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT service, country_name, country_code, rate, traffic FROM rates ORDER BY service ASC, country_name ASC") as cur:
            all_rates = await cur.fetchall()

    if not all_rates:
        await message.answer(
            "📊 <b>বর্তমান সার্ভিস ও কান্ট্রি রেট:</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ বর্তমানে কোনো দেশের রেট ও ট্রাফিক ডাটাবেজে নেই।\n"
            "অ্যাডমিন প্যানেল (🛠 ADMIN PANEL) থেকে <b>'🌍 দেশ, রেট ও ট্রাফিক'</b> অপশনে গিয়ে রেট যোগ করুন।\n━━━━━━━━━━━━━━━━━━━━━"
        )
        return

    text = "📊 <b>বর্তমান সার্ভিস, রেট ও ট্রাফিক তালিকা:</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    current_srv = None
    for srv, c_name, c_code, rate, traffic in all_rates:
        if srv != current_srv:
            current_srv = srv
            text += f"🔹 <b>{srv}</b>\n"
        text += f"   ▫️ {c_name} ({c_code}) — <b>{rate:.2f} ৳/OTP</b> | {traffic}\n"
    text += "\n━━━━━━━━━━━━━━━━━━━━━"
    await message.answer(text)

# --- ইউজার বাটন: 👥 SUPPORT ---
@dp.message(F.text.in_(["👥 SUPPORT", "SUPPORT"]))
async def show_support(message: types.Message):
    sup_user = await get_setting("support_username")
    sup_clean = sup_user.strip().lstrip("@") if sup_user else "telegram"
    support_url = f"https://t.me/{sup_clean}"

    support_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Support", url=support_url)],
        [InlineKeyboardButton(text="❌ Close", callback_data="close_box")]
    ])
    await message.answer("💬 <b>Contact us for any help:</b>", reply_markup=support_kb)

# --- ইউজার বাটন: 👤 PROFILE ---
@dp.message(F.text.in_(["👤 PROFILE", "PROFILE"]))
async def show_profile(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT balance, total_refers, daily_otps, daily_income, total_otps, total_income FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()

    balance, refers, d_otps, d_income, t_otps, t_income = row if row else (0, 0, 0, 0, 0, 0)

    profile_text = (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>YOUR PROFILE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔢 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"👛 <b>Balance:</b> {balance:.2f} ৳\n"
        f"🤝 <b>Total Refers:</b> {refers}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📅 <b>TODAY</b>\n"
        f"🛡 <b>Daily OTPs:</b> {d_otps}\n"
        f"💲 <b>Daily Income:</b> {d_income:.2f} ৳\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 <b>ALL TIME</b>\n"
        f"🛡 <b>Total OTPs:</b> {t_otps}\n"
        f"💲 <b>Total Income:</b> {t_income:.2f} ৳\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

    profile_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 REFER", callback_data="refer_link")],
        [InlineKeyboardButton(text="❌ Close", callback_data="close_box")]
    ])
    await message.answer(profile_text, reply_markup=profile_kb)

# --- ইউজার বাটন: 👑 LEADERBOARD ---
@dp.message(F.text.in_(["👑 LEADERBOARD", "LEADERBOARD"]))
async def show_leaderboard(message: types.Message):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT user_id, total_income FROM users ORDER BY total_income DESC LIMIT 10") as cur:
            top_users = await cur.fetchall()

    text = "👑 <b>শীর্ষ আর্নার তালিকা (Leaderboard):</b>\n━━━━━━━━━━━━━━━━━━━━━\n"
    if not top_users:
        text += "বর্তমানে কোনো আর্নার তালিকা নেই।\n"
    else:
        for idx, (uid, inc) in enumerate(top_users, start=1):
            masked_uid = str(uid)[:4] + "***"
            text += f"{idx}. ID: <code>{masked_uid}</code> — <b>{inc:.2f} ৳</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━"
    await message.answer(text)

# --- ইউজার বাটন: 📅 WITHDRAWAL ---
@dp.message(F.text.in_(["📅 WITHDRAWAL", "WITHDRAWAL"]))
async def user_withdraw_start(message: types.Message, state: FSMContext):
    await state.clear()
    methods_str = await get_setting("withdraw_methods")
    min_w = await get_setting("min_withdraw") or "50"
    
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
            balance = row[0] if row else 0.0

    methods = parse_methods(methods_str)
    method_buttons = []
    row = []
    for m in methods:
        row.append(InlineKeyboardButton(text=f"💳 {m}", callback_data=f"wmethod:{m}"))
        if len(row) == 2:
            method_buttons.append(row)
            row = []
    if row:
        method_buttons.append(row)
        
    method_buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="close_box")])

    await message.answer(
        f"💳 <b>উইথড্রয়াল মেনু</b>\n\n"
        f"💰 আপনার বর্তমান ব্যালেন্স: <b>{balance:.2f} ৳</b>\n"
        f"⚠️ সর্বনিম্ন উইথড্র: <b>{min_w} ৳</b>\n\n"
        f"টাকা তোলার মাধ্যম সিলেক্ট করুন:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=method_buttons)
    )

@dp.callback_query(F.data.startswith("wmethod:"))
async def withdraw_select_method(callback: types.CallbackQuery, state: FSMContext):
    method = callback.data.split("wmethod:")[1]
    await state.update_data(method=method)
    await state.set_state(WithdrawStates.waiting_account)
    await callback.message.edit_text(
        f"আপনার <b>{method}</b> অ্যাকাউন্ট নাম্বারটি লিখে মেসেজ পাঠান:\n\n(বাতিল করতে চাইলে /cancel লিখুন)"
    )

@dp.message(WithdrawStates.waiting_account)
async def withdraw_get_account(message: types.Message, state: FSMContext):
    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ উইথড্র বাতিল করা হয়েছে।")
        return
    await state.update_data(account=message.text.strip())
    await state.set_state(WithdrawStates.waiting_amount)
    await message.answer("কত টাকা তুলতে চান? (সংখ্যায় লিখুন, যেমন: 50):")

@dp.message(WithdrawStates.waiting_amount)
async def withdraw_get_amount(message: types.Message, state: FSMContext):
    if message.text.strip() == "/cancel":
        await state.clear()
        await message.answer("❌ উইথড্র বাতিল করা হয়েছে।")
        return
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("অনুগ্রহ করে সঠিক সংখ্যায় লিখুন (যেমন: 50):")
        return

    min_w = float(await get_setting("min_withdraw") or 50)
    if amount < min_w:
        await message.answer(f"❌ সর্বনিম্ন উইথড্র {min_w} ৳ হতে হবে। আবার পরিমাণ লিখুন:")
        return

    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
            balance = row[0] if row else 0.0

    if amount > balance:
        await message.answer(f"❌ আপনার ব্যালেন্স পর্যাপ্ত নয়!\nবর্তমান ব্যালেন্স: {balance:.2f} ৳\nউইথড্র বাতিল হয়েছে।")
        await state.clear()
        return

    data = await state.get_data()
    method = data["method"]
    account = data["account"]

    async with aiosqlite.connect("database.db") as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, message.from_user.id))
        await db.execute("INSERT INTO withdrawals (user_id, method, account, amount) VALUES (?, ?, ?, ?)",
                         (message.from_user.id, method, account, amount))
        await db.commit()

    await state.clear()
    await message.answer(f"✅ আপনার <b>{amount:.2f} ৳</b> এর <b>{method}</b> উইথড্র রিকোয়েস্ট সফলভাবে জমা হয়েছে।")

@dp.callback_query(F.data == "close_box")
async def close_box(callback: types.CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data == "refer_link")
async def show_refer(callback: types.CallbackQuery):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    await callback.answer(f"আপনার রেফার লিংক:\n{ref_link}", show_alert=True)

# ==============================================================
#                  🛠 সম্পূর্ণ অ্যাডমিন প্যানেল 🛠
# ==============================================================
async def get_admin_keyboard():
    mode = await get_setting("api_mode")
    mode_text = "🟢 মোড: অটো API" if mode == "AUTO" else "🟡 মোড: ম্যানুয়াল DB"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ সার্ভিস যোগ", callback_data="adm_add_srv"),
         InlineKeyboardButton(text="🌍 দেশ, রেট ও ট্রাফিক", callback_data="adm_add_rate")],
        [InlineKeyboardButton(text="📱 ম্যানুয়াল নম্বর আপলোড", callback_data="adm_add_nums"),
         InlineKeyboardButton(text="📩 ম্যানুয়াল ওটিপি সেন্ড", callback_data="adm_send_otp")],
        [InlineKeyboardButton(text=mode_text, callback_data="adm_toggle_mode"),
         InlineKeyboardButton(text="📋 সকল রেট ও ট্রাফিক", callback_data="adm_view_rates")],
        [InlineKeyboardButton(text="🔑 SMS API Key", callback_data="adm_api_key"),
         InlineKeyboardButton(text="🌐 SMS API URL", callback_data="adm_api_url")],
        [InlineKeyboardButton(text="📢 OTP চ্যানেল আইডি", callback_data="adm_chan_id"),
         InlineKeyboardButton(text="🔗 OTP গ্রুপ লিংক", callback_data="adm_grp_link")],
        [InlineKeyboardButton(text="🎬 YouTube লিংক", callback_data="adm_yt_link"),
         InlineKeyboardButton(text="👤 সাপোর্ট ইউজারনেম", callback_data="adm_support")],
        [InlineKeyboardButton(text="💳 উইথড্র মেথডস", callback_data="adm_w_methods"),
         InlineKeyboardButton(text="💰 মিনিমাম উইথড্র", callback_data="adm_min_w")],
        [InlineKeyboardButton(text="❌ প্যানেল বন্ধ", callback_data="close_box")]
    ])

@dp.message(F.text == "🛠 ADMIN PANEL")
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = await get_admin_keyboard()
    await message.answer("🛠 <b>বট কন্ট্রোল ও অ্যাডমিন প্যানেল</b>\n\nনিচের অপশনগুলো থেকে বট পরিচালনা করুন:", reply_markup=kb)

@dp.callback_query(F.data == "adm_toggle_mode")
async def toggle_api_mode(cb: types.CallbackQuery):
    curr = await get_setting("api_mode")
    new_mode = "MANUAL" if curr == "AUTO" else "AUTO"
    await set_setting("api_mode", new_mode)
    await cb.answer(f"মোড পরিবর্তিত হয়েছে: {new_mode}", show_alert=True)
    kb = await get_admin_keyboard()
    await cb.message.edit_reply_markup(reply_markup=kb)

@dp.callback_query(F.data == "adm_add_srv")
async def adm_add_service_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("নতুন সার্ভিসের নাম লিখুন (যেমন: TELEGRAM, TIKTOK, FACEBOOK):")
    await state.set_state(AdminStates.waiting_new_service_name)

@dp.message(AdminStates.waiting_new_service_name)
async def adm_add_service_step2(message: types.Message, state: FSMContext):
    await state.update_data(srv_name=message.text.strip().upper())
    await message.answer("SMS API সার্ভিস কোড দিন (যেমন: Telegram এর জন্য <code>tg</code>):")
    await state.set_state(AdminStates.waiting_new_service_code)

@dp.message(AdminStates.waiting_new_service_code)
async def adm_add_service_finish(message: types.Message, state: FSMContext):
    api_code = message.text.strip().lower()
    data = await state.get_data()
    srv_name = data['srv_name']
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO services (name, api_code) VALUES (?, ?)", (srv_name, api_code))
        await db.commit()
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer(f"✅ <b>{srv_name}</b> সার্ভিস সফলভাবে যোগ করা হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_rate")
async def adm_add_rate_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("সার্ভিসের নাম লিখুন (যেমন: <b>TELEGRAM</b>):")
    await state.set_state(AdminStates.waiting_rate_service)

@dp.message(AdminStates.waiting_rate_service)
async def adm_rate_step2(message: types.Message, state: FSMContext):
    srv = message.text.strip().upper()
    await state.update_data(service=srv)
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR IGNORE INTO services (name, api_code) VALUES (?, ?)", (srv, srv[:2].lower()))
        await db.commit()
    await message.answer("দেশের নাম লিখুন (যেমন: <b>ZIMBABWE</b>):")
    await state.set_state(AdminStates.waiting_rate_cname)

@dp.message(AdminStates.waiting_rate_cname)
async def adm_rate_step3(message: types.Message, state: FSMContext):
    await state.update_data(cname=message.text.strip().upper())
    await message.answer("দেশের ২ অক্ষরের কান্ট্রি কোড লিখুন (যেমন: <b>ZW</b>):")
    await state.set_state(AdminStates.waiting_rate_ccode)

@dp.message(AdminStates.waiting_rate_ccode)
async def adm_rate_step4(message: types.Message, state: FSMContext):
    await state.update_data(ccode=message.text.strip().upper())
    await message.answer("কান্ট্রি ডায়াল কোড লিখুন (যেমন: <b>+263</b>):")
    await state.set_state(AdminStates.waiting_rate_dial)

@dp.message(AdminStates.waiting_rate_dial)
async def adm_rate_step5(message: types.Message, state: FSMContext):
    await state.update_data(dial=message.text.strip())
    await message.answer("প্রতি ওটিপিতে ইউজার কত টাকা পাবে তা লিখুন (যেমন: <b>0.65</b>):")
    await state.set_state(AdminStates.waiting_rate_amount)

@dp.message(AdminStates.waiting_rate_amount)
async def adm_rate_step6(message: types.Message, state: FSMContext):
    try:
        rate = float(message.text.strip())
    except ValueError:
        await message.answer("❌ সঠিক সংখ্যা লিখুন:")
        return
    await state.update_data(rate=rate)
    traffic_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 High Traffic", callback_data="traffic_🟢 High Traffic")],
        [InlineKeyboardButton(text="🟡 Medium Traffic", callback_data="traffic_🟡 Medium Traffic")],
        [InlineKeyboardButton(text="🔴 Slow Traffic", callback_data="traffic_🔴 Slow Traffic")]
    ])
    await message.answer("এই দেশের ট্রাফিক স্ট্যাটাস সিলেক্ট করুন:", reply_markup=traffic_kb)

@dp.callback_query(F.data.startswith("traffic_"))
async def adm_rate_traffic_chosen(cb: types.CallbackQuery, state: FSMContext):
    traffic = cb.data.split("traffic_")[1]
    data = await state.get_data()
    async with aiosqlite.connect("database.db") as db:
        await db.execute(
            "INSERT INTO rates (service, country_name, country_code, dial_code, rate, traffic) VALUES (?, ?, ?, ?, ?, ?)",
            (data['service'], data['cname'], data['ccode'], data['dial'], data['rate'], traffic)
        )
        await db.commit()
    await state.clear()
    kb = await get_admin_keyboard()
    await cb.message.edit_text(f"✅ <b>দেশ ও রেট সফলভাবে যুক্ত হয়েছে!</b>", reply_markup=kb)

@dp.callback_query(F.data == "adm_view_rates")
async def adm_view_rates(cb: types.CallbackQuery):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT id, service, country_name, country_code, rate, traffic FROM rates") as cur:
            rows = await cur.fetchall()
    if not rows:
        empty_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ নতুন রেট যোগ করুন", callback_data="adm_add_rate")],
            [InlineKeyboardButton(text="⬅️ ব্যাক", callback_data="adm_back_menu")]
        ])
        await cb.message.edit_text("📋 <b>বর্তমানে কোনো রেট ও ট্রাফিক ডাটাবেজে নেই!</b>", reply_markup=empty_kb)
        return
    txt = "📋 <b>ডাটাবেজে থাকা রেট ও ট্রাফিক তালিকা:</b>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    for r_id, srv, cn, ccode, rt, trf in rows:
        txt += f"🆔 <b>{r_id}</b> | <b>{srv}</b> | {cn} ({ccode}) | <b>{rt:.2f} ৳</b> | {trf}\n"
    view_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ নতুন রেট যোগ", callback_data="adm_add_rate"),
         InlineKeyboardButton(text="🗑 রেট মুছুন", callback_data="adm_del_rate")],
        [InlineKeyboardButton(text="⬅️ ব্যাক", callback_data="adm_back_menu")]
    ])
    await cb.message.edit_text(txt, reply_markup=view_kb)

@dp.callback_query(F.data == "adm_del_rate")
async def adm_del_rate_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("যে রেটটি মুছতে চান তার 🆔 নম্বরটি লিখে পাঠান:")
    await state.set_state(AdminStates.waiting_delete_rate_id)

@dp.message(AdminStates.waiting_delete_rate_id)
async def adm_del_rate_finish(message: types.Message, state: FSMContext):
    try:
        r_id = int(message.text.strip())
        async with aiosqlite.connect("database.db") as db:
            await db.execute("DELETE FROM rates WHERE id = ?", (r_id,))
            await db.commit()
        await state.clear()
        kb = await get_admin_keyboard()
        await message.answer(f"✅ 🆔 <b>{r_id}</b> রেটটি মুছে ফেলা হয়েছে!", reply_markup=kb)
    except Exception:
        await message.answer("❌ সঠিক আইডি নম্বর দিন:")

@dp.callback_query(F.data == "adm_back_menu")
async def adm_back_menu(cb: types.CallbackQuery):
    kb = await get_admin_keyboard()
    await cb.message.edit_text("🛠 <b>বট কন্ট্রোল ও অ্যাডমিন প্যানেল</b>\n\nনিচের অপশনগুলো থেকে বট পরিচালনা করুন:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_nums")
async def adm_add_nums_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("কোন সার্ভিসের জন্য নাম্বার দিবেন? (যেমন: TELEGRAM):")
    await state.set_state(AdminStates.waiting_num_service)

@dp.message(AdminStates.waiting_num_service)
async def adm_add_nums_step2(message: types.Message, state: FSMContext):
    await state.update_data(service=message.text.strip().upper())
    await message.answer("দেশের ২ অক্ষরের কান্ট্রি কোড লিখুন (যেমন: ZW):")
    await state.set_state(AdminStates.waiting_num_country)

@dp.message(AdminStates.waiting_num_country)
async def adm_add_nums_step3(message: types.Message, state: FSMContext):
    await state.update_data(ccode=message.text.strip().upper())
    await message.answer("ফোন নাম্বারগুলো লিখে পাঠান (প্রতি লাইনে একটি করে):")
    await state.set_state(AdminStates.waiting_numbers_input)

@dp.message(AdminStates.waiting_numbers_input)
async def adm_add_nums_finish(message: types.Message, state: FSMContext):
    raw_text = message.text.strip()
    lines = raw_text.split("\n")
    data = await state.get_data()
    srv = data['service']
    ccode = data['ccode']
    count = 0
    async with aiosqlite.connect("database.db") as db:
        for line in lines:
            num = line.strip()
            if num:
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO numbers (service, country_code, phone_number, status) VALUES (?, ?, ?, 'AVAILABLE')",
                        (srv, ccode, num)
                    )
                    count += 1
                except Exception:
                    pass
        await db.commit()
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer(f"✅ মোট <b>{count}</b> টি নম্বর ডাটাবেজে যুক্ত হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_send_otp")
async def adm_send_otp_start(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.edit_text("ফোন নম্বরটি লিখুন (যেমন: +263785275846):")
    await state.set_state(AdminStates.waiting_otp_number)

@dp.message(AdminStates.waiting_otp_number)
async def adm_send_otp_step2(message: types.Message, state: FSMContext):
    await state.update_data(otp_number=message.text.strip())
    await message.answer("ওটিপি কোডটি লিখুন (যেমন: 83159):")
    await state.set_state(AdminStates.waiting_otp_code)

@dp.message(AdminStates.waiting_otp_code)
async def adm_send_otp_finish(message: types.Message, state: FSMContext):
    otp_code = message.text.strip()
    data = await state.get_data()
    phone_number = data['otp_number']
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT service, country_code, assigned_to FROM numbers WHERE phone_number = ?", (phone_number,)) as cur:
            num_row = await cur.fetchone()
    if not num_row:
        kb = await get_admin_keyboard()
        await message.answer(f"❌ ডাটাবেজে <code>{phone_number}</code> নম্বরটি পাওয়া যায়নি!", reply_markup=kb)
        await state.clear()
        return
    srv, country_code, assigned_user = num_row
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT rate FROM rates WHERE service = ? AND country_code = ?", (srv, country_code)) as r_cur:
            rate_row = await r_cur.fetchone()
            rate = rate_row[0] if rate_row else 0.65
    target_user = assigned_user if assigned_user else ADMIN_ID
    await deliver_otp_success(target_user, phone_number, otp_code, country_code, rate)
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer(f"✅ ওটিপি পাঠানো সম্পন্ন হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_api_key")
async def adm_set_apikey(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("sms_api_key")
    await cb.message.edit_text(f"বর্তমান API Key: <code>{curr}</code>\n\nনতুন SMS API Key লিখে মেসেজ দিন:")
    await state.set_state(AdminStates.waiting_api_key)

@dp.message(AdminStates.waiting_api_key)
async def save_api_key(message: types.Message, state: FSMContext):
    await set_setting("sms_api_key", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ API Key সফলভাবে আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_api_url")
async def adm_set_apiurl(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("sms_api_url")
    await cb.message.edit_text(f"বর্তমান API URL: <code>{curr}</code>\n\nনতুন API URL লিখে মেসেজ দিন:")
    await state.set_state(AdminStates.waiting_api_url)

@dp.message(AdminStates.waiting_api_url)
async def save_api_url(message: types.Message, state: FSMContext):
    await set_setting("sms_api_url", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ SMS API URL আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_chan_id")
async def adm_set_channel(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("otp_channel_id")
    await cb.message.edit_text(f"বর্তমান চ্যানেল আইডি: <code>{curr}</code>\n\nযে চ্যানেলে ওটিপি পোস্ট হবে তার আইডি দিন:")
    await state.set_state(AdminStates.waiting_channel_id)

@dp.message(AdminStates.waiting_channel_id)
async def save_channel_id(message: types.Message, state: FSMContext):
    await set_setting("otp_channel_id", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ ওটিপি চ্যানেল আইডি আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_grp_link")
async def adm_set_grplink(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("otp_group_link")
    await cb.message.edit_text(f"বর্তমান গ্রুপ লিংক: {curr}\n\nনতুন গ্রুপ লিংক দিন:")
    await state.set_state(AdminStates.waiting_group_link)

@dp.message(AdminStates.waiting_group_link)
async def save_group_link(message: types.Message, state: FSMContext):
    await set_setting("otp_group_link", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ ওটিপি গ্রুপ লিংক আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_yt_link")
async def adm_set_ytlink(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("youtube_link")
    await cb.message.edit_text(f"বর্তমান YouTube লিংক: {curr}\n\nনতুন YouTube লিংক দিন:")
    await state.set_state(AdminStates.waiting_yt_link)

@dp.message(AdminStates.waiting_yt_link)
async def save_yt_link(message: types.Message, state: FSMContext):
    await set_setting("youtube_link", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ YouTube লিংক আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_support")
async def adm_set_support(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("support_username")
    await cb.message.edit_text(f"বর্তমান সাপোর্ট আইডি: <code>{curr}</code>\n\nনতুন সাপোর্ট ইউজারনেম দিন (যেমন @YourSupportUser):")
    await state.set_state(AdminStates.waiting_support_user)

@dp.message(AdminStates.waiting_support_user)
async def save_support_user(message: types.Message, state: FSMContext):
    await set_setting("support_username", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ সাপোর্ট ইউজারনেম আপডেট হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_w_methods")
async def adm_set_methods(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("withdraw_methods")
    await cb.message.edit_text(f"বর্তমান মেথডস: <code>{curr}</code>\n\nকমা দিয়ে নতুন মেথডস লিখুন:")
    await state.set_state(AdminStates.waiting_withdraw_methods)

@dp.message(AdminStates.waiting_withdraw_methods)
async def save_withdraw_methods(message: types.Message, state: FSMContext):
    methods_list = parse_methods(message.text.strip())
    clean_val = ", ".join(methods_list)
    await set_setting("withdraw_methods", clean_val)
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer(f"✅ উইথড্র মেথডস সফলভাবে সেভ হয়েছে!", reply_markup=kb)

@dp.callback_query(F.data == "adm_min_w")
async def adm_set_min_w(cb: types.CallbackQuery, state: FSMContext):
    curr = await get_setting("min_withdraw")
    await cb.message.edit_text(f"বর্তমান মিনিমাম উইথড্র: <code>{curr} ৳</code>\n\nনতুন পরিমাণ দিন:")
    await state.set_state(AdminStates.waiting_min_withdraw)

@dp.message(AdminStates.waiting_min_withdraw)
async def save_min_w(message: types.Message, state: FSMContext):
    await set_setting("min_withdraw", message.text.strip())
    await state.clear()
    kb = await get_admin_keyboard()
    await message.answer("✅ মিনিমাম উইথড্র আপডেট হয়েছে!", reply_markup=kb)

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