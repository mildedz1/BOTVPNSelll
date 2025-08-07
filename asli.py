# -*- coding: utf-8 -*-
import sqlite3
import logging
import uuid
import asyncio
import requests
import csv
import io
from datetime import datetime, timedelta, time
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    TypeHandler,
    ApplicationHandlerStop,
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError, Forbidden, BadRequest

# --- Basic Settings ---
BOT_TOKEN = "7910215097:AAH-Zalti5nDFPTS8Dokw0Tgcgb3EpibGEc"
ADMIN_ID = 6839887159
CHANNEL_USERNAME = "@wings_iran"
CHANNEL_ID = -1001553094061
DB_NAME = "bot.db"

# --- Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Conversation States (Only for multi-step processes) ---
(
    ADMIN_MAIN_MENU,
    # Plan Management
    ADMIN_PLAN_MENU, ADMIN_PLAN_AWAIT_NAME, ADMIN_PLAN_AWAIT_DESC,
    ADMIN_PLAN_AWAIT_PRICE, ADMIN_PLAN_AWAIT_DAYS, ADMIN_PLAN_AWAIT_GIGABYTES,
    ADMIN_PLAN_EDIT_MENU, ADMIN_PLAN_EDIT_AWAIT_VALUE,
    # Settings Management
    SETTINGS_MENU, SETTINGS_AWAIT_TRIAL_DAYS, SETTINGS_AWAIT_PAYMENT_TEXT,
    # User Purchase Flow
    SELECT_PLAN, AWAIT_PAYMENT_SCREENSHOT, AWAIT_DISCOUNT_CODE,
    # Admin Stats
    ADMIN_STATS_MENU,
    # Message & Button Editor
    ADMIN_MESSAGES_MENU, ADMIN_MESSAGES_SELECT, ADMIN_MESSAGES_EDIT_TEXT,
    ADMIN_BUTTON_ADD_AWAIT_TEXT, ADMIN_BUTTON_ADD_AWAIT_TARGET,
    ADMIN_BUTTON_ADD_AWAIT_URL, ADMIN_BUTTON_ADD_AWAIT_ROW, ADMIN_BUTTON_ADD_AWAIT_COL,
    # New Message Creation
    ADMIN_MESSAGES_ADD_AWAIT_NAME, ADMIN_MESSAGES_ADD_AWAIT_CONTENT,
    # Card Management
    ADMIN_CARDS_MENU, ADMIN_CARDS_AWAIT_NUMBER, ADMIN_CARDS_AWAIT_HOLDER,
    # Broadcast
    BROADCAST_SELECT_AUDIENCE, BROADCAST_AWAIT_MESSAGE,
    # Renewal Flow States
    RENEW_SELECT_PLAN, RENEW_AWAIT_PAYMENT, RENEW_AWAIT_DISCOUNT_CODE,
    # Discount Code Management
    DISCOUNT_MENU, DISCOUNT_AWAIT_CODE, DISCOUNT_AWAIT_PERCENT,
    DISCOUNT_AWAIT_LIMIT, DISCOUNT_AWAIT_EXPIRY,
    # Multi-Panel Management
    ADMIN_PANELS_MENU, ADMIN_PANEL_AWAIT_NAME, ADMIN_PANEL_AWAIT_URL,
    ADMIN_PANEL_AWAIT_USER, ADMIN_PANEL_AWAIT_PASS,
    # Backup
    BACKUP_CHOOSE_PANEL,
    # Panel Inbound Management (NEW)
    ADMIN_PANEL_INBOUNDS_MENU, ADMIN_PANEL_INBOUNDS_AWAIT_PROTOCOL, ADMIN_PANEL_INBOUNDS_AWAIT_TAG,
) = range(48)


# --- Database Management ---
def db_setup():
    with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
        cursor = conn.cursor()
        # --- Create Tables ---
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, join_date TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS messages (message_name TEXT PRIMARY KEY, text TEXT, file_id TEXT, file_type TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS buttons (id INTEGER PRIMARY KEY AUTOINCREMENT, menu_name TEXT, text TEXT, target TEXT, is_url BOOLEAN DEFAULT 0, row INTEGER, col INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, price INTEGER NOT NULL, duration_days INTEGER NOT NULL, traffic_gb REAL NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY AUTOINCREMENT, card_number TEXT NOT NULL, holder_name TEXT NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS free_trials (user_id INTEGER PRIMARY KEY, timestamp TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS discount_codes (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, percentage INTEGER NOT NULL, usage_limit INTEGER NOT NULL, times_used INTEGER DEFAULT 0, expiry_date TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS panels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, url TEXT NOT NULL, username TEXT NOT NULL, password TEXT NOT NULL)")
        # --- NEW: Table for manually setting inbounds for each panel ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS panel_inbounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id INTEGER NOT NULL,
                protocol TEXT NOT NULL,
                tag TEXT NOT NULL,
                UNIQUE(panel_id, tag),
                FOREIGN KEY (panel_id) REFERENCES panels(id) ON DELETE CASCADE
            )""")

        # --- Check if 'orders' table exists before altering ---
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(orders)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'panel_id' not in columns: cursor.execute("ALTER TABLE orders ADD COLUMN panel_id INTEGER")
            if 'discount_code' not in columns: cursor.execute("ALTER TABLE orders ADD COLUMN discount_code TEXT")
            if 'final_price' not in columns: cursor.execute("ALTER TABLE orders ADD COLUMN final_price INTEGER")
            if 'last_reminder_date' not in columns: cursor.execute("ALTER TABLE orders ADD COLUMN last_reminder_date TEXT")
        else:
            cursor.execute("""
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending', marzban_username TEXT, screenshot_file_id TEXT, timestamp TEXT,
                    panel_id INTEGER, discount_code TEXT, final_price INTEGER, last_reminder_date TEXT
                )""")
        conn.commit()
        initialize_default_content(cursor, conn)

def initialize_default_content(cursor, conn):
    default_messages = {
        'start_main': ('\U0001F44B سلام! به ربات فروش کانفیگ ما خوش آمدید.\nبرای شروع از دکمه\u200cهای زیر استفاده کنید.', None, None),
        'admin_panel_main': ('\U0001F5A5\uFE0F پنل مدیریت ربات. لطفا یک گزینه را انتخاب کنید.', None, None),
        'buy_config_main': ('\U0001F4E1 **خرید کانفیگ**\n\nلطفا یکی از پلن\u200cهای زیر را انتخاب کنید:', None, None),
        'payment_info_text': ('\U0001F4B3 **اطلاعات پرداخت** \U0001F4B3\n\nمبلغ پلن انتخابی را به یکی از کارت\u200cهای زیر واریز کرده و سپس اسکرین\u200cشات رسید را در همین صفحه ارسال نمایید.', None, None),
        'renewal_reminder_text': ('\u26A0\uFE0F **یادآوری تمدید سرویس**\n\nکاربر گرامی، اعتبار سرویس شما با نام کاربری `{marzban_username}` رو به اتمام است.\n\n{details}\n\nبرای جلوگیری از قطع شدن سرویس، لطفاً از طریق دکمه "سرویس من" در منوی اصلی ربات اقدام به تمدید نمایید.', None, None)
    }
    for name, (text, f_id, f_type) in default_messages.items():
        cursor.execute("INSERT OR IGNORE INTO messages (message_name, text, file_id, file_type) VALUES (?, ?, ?, ?)", (name, text, f_id, f_type))

    conn.commit()

    if not query_db("SELECT 1 FROM buttons WHERE menu_name = 'start_main'", one=True):
        default_buttons = [
            ('\U0001F680 خرید کانفیگ', 'buy_config_main', 0, 1, 1),
            ('\U0001F4E6 سرویس من', 'my_services', 0, 1, 2),
            ('\U0001F3AB کانفیگ تست رایگان', 'get_free_config', 0, 2, 1),
        ]
        for btn_text, btn_target, btn_is_url, btn_row, btn_col in default_buttons:
             execute_db("INSERT INTO buttons (menu_name, text, target, is_url, row, col) VALUES (?, ?, ?, ?, ?, ?)", ('start_main', btn_text, btn_target, btn_is_url, btn_row, btn_col))

    if not query_db("SELECT 1 FROM panels", one=True):
        url_row = query_db("SELECT value FROM settings WHERE key = 'panel_url'", one=True)
        user_row = query_db("SELECT value FROM settings WHERE key = 'panel_user'", one=True)
        password_row = query_db("SELECT value FROM settings WHERE key = 'panel_pass'", one=True)

        url = url_row.get('value') if url_row else 'https://your-panel.com'
        user = user_row.get('value') if user_row else 'admin'
        password = password_row.get('value') if password_row else 'password'

        execute_db("INSERT INTO panels (name, url, username, password) VALUES (?, ?, ?, ?)", ('پنل اصلی (پیش‌فرض)', url, user, password))
        execute_db("DELETE FROM settings WHERE key IN ('panel_url', 'panel_user', 'panel_pass')")

    default_settings = {'free_trial_days': '1', 'free_trial_gb': '0.2', 'free_trial_status': '1'}
    for key, value in default_settings.items():
        execute_db("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    if not query_db("SELECT 1 FROM cards", one=True):
        execute_db("INSERT INTO cards (card_number, holder_name) VALUES (?, ?)", ("6037-0000-0000-0000", "نام دارنده کارت"))


def query_db(query, args=(), one=False):
    try:
        with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, args)
            r = cursor.fetchall()
            return (dict(r[0]) if r and r[0] else None) if one else [dict(row) for row in r]
    except sqlite3.Error as e:
        logger.error(f"DB query error: {e}")
        return None if one else []

def execute_db(query, args=()):
    try:
        with sqlite3.connect(DB_NAME, check_same_thread=False) as conn:
            cursor = conn.cursor()
            cursor.execute(query, args)
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"DB execute error: {e}")
        return None

# --- VPN Panel API ---
class VpnPanelAPI:
    def __init__(self, panel_id: int):
        panel_data = query_db("SELECT * FROM panels WHERE id = ?", (panel_id,), one=True)
        if not panel_data:
            raise ValueError(f"Panel with ID {panel_id} not found in database.")
        self.panel_id = panel_id # Store panel_id for later use
        self.base_url = panel_data['url'].rstrip('/')
        self.username = panel_data['username']
        self.password = panel_data['password']
        self.session = requests.Session()
        self.access_token = None

    def get_token(self):
        if not all([self.base_url, self.username, self.password]):
            logger.error("Marzban panel credentials are not set for this panel.")
            return False
        try:
            r = self.session.post(f"{self.base_url}/api/admin/token", data={'username': self.username, 'password': self.password}, headers={'Content-Type': 'application/x-www-form-urlencoded', 'accept': 'application/json'}, timeout=10)
            r.raise_for_status()
            self.access_token = r.json().get('access_token')
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to get Marzban token for {self.base_url}: {e}")
            return False

    async def get_all_users(self):
        if not self.access_token and not self.get_token(): return None, "خطا در اتصال به پنل"
        headers = {'Authorization': f'Bearer {self.access_token}', 'accept': 'application/json'}
        try:
            r = self.session.get(f"{self.base_url}/api/users", headers=headers, timeout=20)
            r.raise_for_status()
            return r.json().get('users', []), "Success"
        except requests.RequestException as e:
            logger.error(f"Failed to get all users from {self.base_url}: {e}")
            return None, f"خطای پنل: {e}"

    async def get_user(self, marzban_username):
        if not self.access_token and not self.get_token(): return None, "خطا در اتصال به پنل"
        headers = {'Authorization': f'Bearer {self.access_token}', 'accept': 'application/json'}
        try:
            r = self.session.get(f"{self.base_url}/api/user/{marzban_username}", headers=headers, timeout=10)
            if r.status_code == 404: return None, "کاربر یافت نشد"
            r.raise_for_status()
            return r.json(), "Success"
        except requests.RequestException as e:
            logger.error(f"Failed to get user {marzban_username}: {e}")
            return None, f"خطای پنل: {e}"

    async def renew_user_in_panel(self, marzban_username, plan):
        current_user_info, message = await self.get_user(marzban_username)
        if not current_user_info: return None, f"کاربر {marzban_username} برای تمدید یافت نشد."
        current_expire = current_user_info.get('expire') or int(datetime.now().timestamp())
        base_timestamp = max(current_expire, int(datetime.now().timestamp()))
        additional_days_in_seconds = int(plan['duration_days']) * 86400
        new_expire_timestamp = base_timestamp + additional_days_in_seconds
        current_data_limit = current_user_info.get('data_limit', 0)
        additional_data_bytes = int(float(plan['traffic_gb']) * 1024 * 1024 * 1024)
        new_data_limit_bytes = current_data_limit + additional_data_bytes
        update_data = { "expire": new_expire_timestamp, "data_limit": new_data_limit_bytes }
        headers = {'Authorization': f'Bearer {self.access_token}', 'accept': 'application/json', 'Content-Type': 'application/json'}
        try:
            r = self.session.put(f"{self.base_url}/api/user/{marzban_username}", json=update_data, headers=headers, timeout=15)
            r.raise_for_status()
            return r.json(), "Success"
        except requests.RequestException as e:
            error_detail = "Unknown error";
            if e.response:
                try: error_detail = e.response.json().get('detail', e.response.text)
                except: error_detail = e.response.text
            logger.error(f"Failed to renew user {marzban_username}: {e} - {error_detail}")
            return None, f"خطای پنل هنگام تمدید: {error_detail}"

    async def create_user(self, user_id, plan):
        """[MODIFIED] Creates a user with manually configured inbounds from the database."""
        if not self.access_token and not self.get_token():
            return None, None, "خطا در اتصال به پنل. لطفا تنظیمات را بررسی کنید."

        # --- MODIFICATION START: Get inbounds from DB instead of API ---
        manual_inbounds = query_db("SELECT protocol, tag FROM panel_inbounds WHERE panel_id = ?", (self.panel_id,))
        if not manual_inbounds:
            return None, None, "خطا: هیچ اینباندی برای این پنل بصورت دستی تنظیم نشده است. لطفا از پنل ادمین، بخش مدیریت پنل‌ها، اینباندها را اضافه کنید."

        inbounds_by_protocol = {}
        for inbound in manual_inbounds:
            protocol = inbound.get('protocol')
            tag = inbound.get('tag')
            if protocol and tag:
                if protocol not in inbounds_by_protocol:
                    inbounds_by_protocol[protocol] = []
                inbounds_by_protocol[protocol].append(tag)

        if not inbounds_by_protocol:
            # This case should be rare if the above check passes, but good for safety
            return None, None, "خطا: اینباندهای تنظیم شده در دیتابیس معتبر نیستند."
        # --- MODIFICATION END ---

        new_username = f"user_{user_id}_{uuid.uuid4().hex[:6]}"
        traffic_gb = float(plan['traffic_gb'])
        data_limit_bytes = int(traffic_gb * 1024 * 1024 * 1024) if traffic_gb > 0 else 0
        expire_timestamp = int((datetime.now() + timedelta(days=int(plan['duration_days']))).timestamp()) if int(plan['duration_days']) > 0 else 0

        proxies_to_add = {}
        for protocol in inbounds_by_protocol.keys():
            proxies_to_add[protocol] = {"flow": "xtls-rprx-vision"} if protocol == "vless" else {}

        user_data = {
            "status": "active",
            "username": new_username,
            "note": "",
            "proxies": proxies_to_add,
            "data_limit": data_limit_bytes,
            "expire": expire_timestamp,
            "data_limit_reset_strategy": "no_reset",
            "inbounds": inbounds_by_protocol
        }

        headers = {'Authorization': f'Bearer {self.access_token}', 'accept': 'application/json', 'Content-Type': 'application/json'}

        try:
            r = self.session.post(f"{self.base_url}/api/user", json=user_data, headers=headers, timeout=15)
            r.raise_for_status()

            user_info = r.json()
            subscription_path = user_info.get('subscription_url')
            if not subscription_path:
                 links = "\n".join(user_info.get('links', []))
                 return new_username, links, "Success"

            full_subscription_link = f"{self.base_url}{subscription_path}" if not subscription_path.startswith('http') else subscription_path

            logger.info(f"Successfully created Marzban user: {new_username} with inbounds: {inbounds_by_protocol}")
            return new_username, full_subscription_link, "Success"

        except requests.RequestException as e:
            error_detail = "Unknown error"
            if e.response:
                try:
                    error_detail_json = e.response.json().get('detail')
                    if isinstance(error_detail_json, list):
                        error_detail = " ".join([d.get('msg', '') for d in error_detail_json if 'msg' in d])
                    elif isinstance(error_detail_json, str):
                        error_detail = error_detail_json
                    else:
                        error_detail = e.response.text
                except:
                    error_detail = e.response.text
            logger.error(f"Failed to create new user: {e} - {error_detail}")
            return None, None, f"خطای پنل: {error_detail}"
# --- Helper Functions ---
async def register_new_user(user: User):
    if not query_db("SELECT 1 FROM users WHERE user_id = ?", (user.id,), one=True):
        execute_db("INSERT INTO users (user_id, first_name, join_date) VALUES (?, ?, ?)",
                   (user.id, user.first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        logger.info(f"Registered new user {user.id} ({user.first_name})")

async def force_join_checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id == ADMIN_ID: return
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user.id)
        if member.status in ['member', 'administrator', 'creator']: return
    except TelegramError as e:
        logger.warning(f"Could not check channel membership for {user.id}: {e}")
        return
    join_url = f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"
    keyboard = [[InlineKeyboardButton("\U0001F195 عضویت در کانال", url=join_url)], [InlineKeyboardButton("\u2705 عضو شدم", callback_data="check_join")]]
    text = f"\u26A0\uFE0F **قفل عضویت**\n\nبرای استفاده از ربات، ابتدا در کانال ما عضو شوید و سپس دکمه «عضو شدم» را بزنید."
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        await update.callback_query.answer("شما هنوز در کانال عضو نیستید!", show_alert=True)
    elif update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    raise ApplicationHandlerStop

# --- Dynamic Message Sender ---
async def send_dynamic_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_name: str, back_to: str = 'start_main'):
    query = update.callback_query

    message_data = query_db("SELECT text, file_id, file_type FROM messages WHERE message_name = ?", (message_name,), one=True)
    if not message_data:
        await query.answer(f"محتوای '{message_name}' یافت نشد!", show_alert=True)
        return

    text = message_data.get('text')
    file_id = message_data.get('file_id')
    file_type = message_data.get('file_type')

    buttons_data = query_db("SELECT text, target, is_url, row, col FROM buttons WHERE menu_name = ? ORDER BY row, col", (message_name,))

    if message_name == 'start_main':
        trial_status = query_db("SELECT value FROM settings WHERE key = 'free_trial_status'", one=True)
        if not trial_status or trial_status.get('value') != '1':
            buttons_data = [b for b in buttons_data if b.get('target') != 'get_free_config']

    keyboard = []
    if buttons_data:
        max_row = max((b['row'] for b in buttons_data), default=0) if buttons_data else 0
        keyboard_rows = [[] for _ in range(max_row + 1)]
        for b in buttons_data:
            btn = InlineKeyboardButton(b['text'], url=b['target']) if b['is_url'] else InlineKeyboardButton(b['text'], callback_data=b['target'])
            if 0 < b['row'] <= len(keyboard_rows):
                keyboard_rows[b['row'] - 1].append(btn)
        keyboard = [row for row in keyboard_rows if row]

    if message_name != 'start_main':
        keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data=back_to)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    try:
        if file_id or (query.message and (query.message.photo or query.message.video or query.message.document)):
            await query.message.delete()
            if file_id:
                sender = getattr(context.bot, f"send_{file_type}")
                await sender(chat_id=query.message.chat_id, file_id=file_id, caption=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            else:
                await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    except TelegramError as e:
        if 'Message is not modified' not in str(e):
            logger.error(f"Error handling dynamic message: {e}")

# --- User Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await register_new_user(update.effective_user)
    context.user_data.clear()

    sender = None
    if update.callback_query:
        sender = update.callback_query.message.edit_text
    elif update.message:
        sender = update.message.reply_text

    if not sender: return ConversationHandler.END

    message_data = query_db("SELECT text FROM messages WHERE message_name = 'start_main'", one=True)
    text = message_data.get('text') if message_data else "خوش آمدید!"

    buttons_data = query_db("SELECT text, target, is_url, row, col FROM buttons WHERE menu_name = 'start_main' ORDER BY row, col")

    trial_status = query_db("SELECT value FROM settings WHERE key = 'free_trial_status'", one=True)
    if not trial_status or trial_status.get('value') != '1':
        buttons_data = [b for b in buttons_data if b.get('target') != 'get_free_config']

    keyboard = []
    if buttons_data:
        max_row = max((b['row'] for b in buttons_data), default=0)
        keyboard_rows = [[] for _ in range(max_row + 1)]
        for b in buttons_data:
            btn = InlineKeyboardButton(b['text'], url=b['target']) if b['is_url'] else InlineKeyboardButton(b['text'], callback_data=b['target'])
            if 0 < b['row'] <= len(keyboard_rows):
                keyboard_rows[b['row'] - 1].append(btn)
        keyboard = [row for row in keyboard_rows if row]

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    await sender(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return ConversationHandler.END

async def get_free_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id

    if query_db("SELECT 1 FROM free_trials WHERE user_id = ?", (user_id,), one=True):
        await context.bot.answer_callback_query(query.id, "شما قبلاً کانفیگ تست خود را دریافت کرده\u200cاید.", show_alert=True)
        return

    first_panel = query_db("SELECT id FROM panels ORDER BY id LIMIT 1", one=True)
    if not first_panel:
        await query.message.edit_text("❌ متاسفانه هیچ پنلی برای ارائه سرویس تنظیم نشده است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت به منو", callback_data='start_main')]]))
        return

    try: await query.message.edit_text("لطفا کمی صبر کنید... \U0001F552")
    except Exception: pass

    settings = {s['key']: s['value'] for s in query_db("SELECT key, value FROM settings WHERE key LIKE 'free_trial_%'")}
    trial_plan = {'traffic_gb': settings.get('free_trial_gb', '0.2'), 'duration_days': settings.get('free_trial_days', '1')}

    panel_api = VpnPanelAPI(panel_id=first_panel['id'])
    marzban_username, config_link, message = await panel_api.create_user(user_id, trial_plan)

    if config_link:
        plan_id_row = query_db("SELECT id FROM plans LIMIT 1", one=True)
        plan_id = plan_id_row['id'] if plan_id_row else -1

        execute_db("INSERT INTO orders (user_id, plan_id, panel_id, status, marzban_username, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                   (user_id, plan_id, first_panel['id'], 'approved', marzban_username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        execute_db("INSERT INTO free_trials (user_id, timestamp) VALUES (?, ?)", (user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        text = (f"✅ کانفیگ تست رایگان شما با موفقیت ساخته شد!\n\n"
                f"<b>حجم:</b> {trial_plan['traffic_gb']} گیگابایت\n"
                f"<b>مدت اعتبار:</b> {trial_plan['duration_days']} روز\n\n"
                f"لینک کانفیگ شما:\n<code>{config_link}</code>\n\n"
                f"<b>آموزش اتصال :</b>\n"
                f"https://t.me/madeingod_tm")
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت به منو", callback_data='start_main')]]))
    else:
        await query.message.edit_text(f"❌ متاسفانه در حال حاضر امکان ارائه کانفیگ تست وجود ندارد.\nخطا: {message}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت به منو", callback_data='start_main')]]))

def bytes_to_gb(byte_val):
    if not byte_val or byte_val == 0: return 0
    return round(byte_val / (1024**3), 2)

async def my_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id

    orders = query_db("SELECT id, marzban_username, plan_id FROM orders WHERE user_id = ? AND status = 'approved' AND marzban_username IS NOT NULL ORDER BY id DESC", (user_id,))

    if not orders:
        await query.message.edit_text("شما در حال حاضر هیچ سرویس فعالی ندارید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='start_main')]]))
        return

    keyboard = []
    text = "شما چندین سرویس فعال دارید. لطفاً یکی را برای مشاهده جزئیات و تمدید انتخاب کنید:\n"
    if len(orders) == 1:
        text = "سرویس فعال شما:"

    for order in orders:
        plan = query_db("SELECT name FROM plans WHERE id = ?", (order['plan_id'],), one=True)
        plan_name = plan['name'] if plan else "سرویس تست/ویژه"
        button_text = f"{plan_name} ({order['marzban_username']})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_service_{order['id']}")])

    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت به منوی اصلی", callback_data='start_main')])
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_specific_service_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split('_')[-1])
    await query.answer()

    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if not order or order['user_id'] != query.from_user.id:
        await query.message.edit_text("خطا: این سرویس یافت نشد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='start_main')]]))
        return

    if not order.get('panel_id'):
        await query.message.edit_text("خطا: اطلاعات پنل برای این سرویس یافت نشد. لطفا با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='my_services')]]))
        return

    try:
        await query.message.edit_text("در حال دریافت اطلاعات سرویس شما... لطفا صبر کنید \U0001F552")
    except TelegramError: pass

    marzban_username = order['marzban_username']
    panel_api = VpnPanelAPI(panel_id=order['panel_id'])
    user_info, message = await panel_api.get_user(marzban_username)

    if not user_info:
        await query.message.edit_text(f"خطا در دریافت اطلاعات از پنل: {message}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='my_services')]]))
        return

    data_limit_gb = "نامحدود" if user_info.get('data_limit', 0) == 0 else f"{bytes_to_gb(user_info.get('data_limit', 0))} گیگابایت"
    data_used_gb = bytes_to_gb(user_info.get('used_traffic', 0))
    expire_date = "نامحدود" if not user_info.get('expire') else datetime.fromtimestamp(user_info['expire']).strftime('%Y-%m-%d')
    sub_link = (f"{panel_api.base_url}{user_info['subscription_url']}") if user_info.get('subscription_url') and not user_info['subscription_url'].startswith('http') else user_info.get('subscription_url', 'لینک یافت نشد')

    text = (f"<b>\U0001F4E6 مشخصات سرویس (<code>{marzban_username}</code>)</b>\n\n"
            f"<b>\U0001F4CA حجم کل:</b> {data_limit_gb}\n"
            f"<b>\U0001F4C8 حجم مصرفی:</b> {data_used_gb} گیگابایت\n"
            f"<b>\U0001F4C5 تاریخ انقضا:</b> {expire_date}\n\n"
            f"<b>\U0001F517 لینک اشتراک:</b>\n<code>{sub_link}</code>")

    keyboard = [
        [InlineKeyboardButton("\U0001F504 تمدید این سرویس", callback_data=f"renew_service_{order_id}")],
        [InlineKeyboardButton("\U0001F519 بازگشت به لیست سرویس‌ها", callback_data='my_services')]
    ]
    await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

# --- Renewal Flow ---
async def start_renewal_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    order_id = int(query.data.split('_')[-1])
    await query.answer()

    context.user_data['renewing_order_id'] = order_id

    plans = query_db("SELECT id, name, price FROM plans ORDER BY price")
    if not plans:
        await query.message.edit_text("در حال حاضر هیچ پلن فعالی برای تمدید وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='my_services')]]))
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"{plan['name']} - {plan['price']:,} تومان", callback_data=f"renew_select_plan_{plan['id']}")] for plan in plans]
    keyboard.append([InlineKeyboardButton("\U0001F519 لغو تمدید", callback_data=f"view_service_{order_id}")])

    text = "\U0001F504 **تمدید سرویس**\n\nلطفا یکی از پلن‌های زیر را برای تمدید انتخاب کنید:"
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    return RENEW_SELECT_PLAN

async def show_renewal_plan_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    plan_id = int(query.data.replace('renew_select_plan_', ''))
    await query.answer()

    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)
    order_id = context.user_data.get('renewing_order_id')

    if not plan or not order_id:
        await query.message.edit_text("خطا: پلن یا سفارش یافت نشد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data=f"view_service_{order_id}")]]))
        return ConversationHandler.END

    context.user_data['selected_renewal_plan_id'] = plan_id
    context.user_data['original_price'] = plan['price']
    context.user_data['final_price'] = plan['price']
    context.user_data['discount_code'] = None

    text = (f"شما پلن زیر را برای تمدید انتخاب کرده\u200cاید:\n\n"
            f"**نام پلن:** {plan['name']}\n"
            f"**قیمت:** {plan['price']:,} تومان\n\n"
            f"آیا تایید می\u200cکنید؟")
    keyboard = [
        [InlineKeyboardButton("\u2705 تایید و پرداخت", callback_data="renew_confirm_purchase")],
        [InlineKeyboardButton("\U0001F381 کد تخفیف دارم", callback_data="renew_apply_discount_start")],
        [InlineKeyboardButton("\U0001F519 لغو", callback_data=f"view_service_{order_id}")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return RENEW_SELECT_PLAN

async def renew_apply_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.edit_text("لطفا کد تخفیف خود را برای تمدید وارد کنید:")
    return RENEW_AWAIT_DISCOUNT_CODE

async def receive_renewal_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    photo_file_id = update.message.photo[-1].file_id
    plan_id = context.user_data.get('selected_renewal_plan_id')
    order_id = context.user_data.get('renewing_order_id')
    final_price = context.user_data.get('final_price')
    discount_code = context.user_data.get('discount_code')


    if not all([plan_id, order_id, final_price is not None]):
        await update.message.reply_text("خطا در فرآیند تمدید. لطفا مجددا تلاش کنید.")
        await start_command(update, context)
        return ConversationHandler.END

    original_order = query_db("SELECT marzban_username FROM orders WHERE id = ?", (order_id,), one=True)
    if not original_order:
         await update.message.reply_text("خطا در یافتن سفارش اصلی. لطفا با پشتیبانی تماس بگیرید.")
         return ConversationHandler.END

    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)

    price_info = f"\U0001F4B0 **مبلغ پرداختی:** {final_price:,} تومان"
    if discount_code:
        price_info += f"\n\U0001F381 **کد تخفیف:** `{discount_code}`"
        # Increment discount code usage upon payment for renewal
        execute_db("UPDATE discount_codes SET times_used = times_used + 1 WHERE code = ?", (discount_code,))


    caption = (f"\u2757 **درخواست تمدید** (برای سفارش #{order_id})\n\n"
               f"**کاربر:** {user.mention_html()} (`{user.id}`)\n"
               f"**نام کاربری مرزبان:** `{original_order['marzban_username']}`\n"
               f"**پلن تمدید:** {plan['name']}\n"
               f"{price_info}\n\n"
               f"لطفا پس از بررسی، تمدید را تایید کنید:")

    keyboard = [[InlineKeyboardButton("\u2705 تایید و تمدید سرویس", callback_data=f"approve_renewal_{order_id}_{plan_id}")]]

    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("✅ رسید شما برای تمدید ارسال شد. لطفا تا زمان تایید نهایی صبور باشید.")

    context.user_data.clear()
    await start_command(update, context)
    return ConversationHandler.END

async def admin_approve_renewal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    *_, order_id, plan_id = query.data.split('_')
    order_id, plan_id = int(order_id), int(plan_id)

    await query.answer("در حال پردازش تمدید...")

    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)

    if not order or not plan:
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u274C **خطا:** سفارش یا پلن یافت نشد.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    if not order.get('panel_id'):
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u274C **خطا:** پنل این کاربر مشخص نیست.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    marzban_username = order['marzban_username']
    if not marzban_username:
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u274C **خطا:** نام کاربری مرزبان برای این سفارش ثبت نشده است.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u23F3 در حال اتصال به پنل و تمدید...", parse_mode=ParseMode.HTML, reply_markup=None)

    panel_api = VpnPanelAPI(panel_id=order['panel_id'])
    renewed_user, message = await panel_api.renew_user_in_panel(marzban_username, plan)

    if renewed_user:
        execute_db("UPDATE orders SET last_reminder_date = NULL WHERE id = ?", (order_id,))
        try:
            await context.bot.send_message(order['user_id'], f"✅ سرویس شما با موفقیت تمدید شد!")
            await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u2705 **تمدید با موفقیت انجام شد.**", parse_mode=ParseMode.HTML, reply_markup=None)
        except TelegramError as e:
            await query.message.edit_caption(caption=query.message.caption_html + f"\n\n\u26A0\uFE0F **تمدید انجام شد اما پیام به کاربر ارسال نشد:** {e}", parse_mode=ParseMode.HTML, reply_markup=None)
    else:
        await query.message.edit_caption(caption=query.message.caption_html + f"\n\n\u274C **خطای پنل هنگام تمدید:**\n`{message}`", parse_mode=ParseMode.HTML, reply_markup=None)

# --- Discount Code Management ---
async def admin_discount_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer()

    codes = query_db("SELECT id, code, percentage, usage_limit, times_used, strftime('%Y-%m-%d', expiry_date) as expiry FROM discount_codes ORDER BY id DESC")

    text = "\U0001F381 **مدیریت کدهای تخفیف**\n\n"
    keyboard = []

    if not codes:
        text += "در حال حاضر هیچ کد تخفیفی ثبت نشده است."
    else:
        text += "کدهای تخفیف:\n"
        for code in codes:
            limit_str = f"{code['times_used']}/{code['usage_limit']}" if code['usage_limit'] > 0 else f"{code['times_used']}/\u221E"
            expiry_str = f"تا {code['expiry']}" if code['expiry'] else "بی‌نهایت"
            info_str = f"{code['code']} ({code['percentage']}%) - {limit_str} - {expiry_str}"
            keyboard.append([
                InlineKeyboardButton(info_str, callback_data=f"noop_{code['id']}"),
                InlineKeyboardButton("\u274C حذف", callback_data=f"delete_discount_{code['id']}")
            ])

    keyboard.insert(0, [InlineKeyboardButton("\u2795 افزودن کد جدید", callback_data="add_discount_code")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت به پنل اصلی", callback_data="admin_main")])

    sender = query.message.edit_text if query else update.message.reply_text
    await sender(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return DISCOUNT_MENU

async def admin_discount_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    code_id = int(query.data.split('_')[-1])
    execute_db("DELETE FROM discount_codes WHERE id = ?", (code_id,))
    await query.answer("کد تخفیف با موفقیت حذف شد.", show_alert=True)
    return await admin_discount_menu(update, context)

async def admin_discount_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data['new_discount'] = {}
    await query.message.edit_text("لطفا **کد تخفیف** را وارد کنید (مثال: `OFF20`):", parse_mode=ParseMode.MARKDOWN)
    return DISCOUNT_AWAIT_CODE

async def admin_discount_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip().upper()
    if query_db("SELECT 1 FROM discount_codes WHERE code = ?", (code,), one=True):
        await update.message.reply_text("این کد تخفیف قبلا ثبت شده. لطفا یک کد دیگر وارد کنید.")
        return DISCOUNT_AWAIT_CODE
    context.user_data['new_discount']['code'] = code
    await update.message.reply_text("لطفا **درصد تخفیف** را به صورت عدد وارد کنید (مثال: `20`):", parse_mode=ParseMode.MARKDOWN)
    return DISCOUNT_AWAIT_PERCENT

async def admin_discount_receive_percent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        percent = int(update.message.text)
        if not 1 <= percent <= 100: raise ValueError()
        context.user_data['new_discount']['percent'] = percent
        await update.message.reply_text("**محدودیت تعداد استفاده** را وارد کنید (برای نامحدود عدد `0` را وارد کنید):", parse_mode=ParseMode.MARKDOWN)
        return DISCOUNT_AWAIT_LIMIT
    except ValueError:
        await update.message.reply_text("ورودی نامعتبر. لطفا فقط یک عدد بین ۱ تا ۱۰۰ وارد کنید.")
        return DISCOUNT_AWAIT_PERCENT

async def admin_discount_receive_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['new_discount']['limit'] = int(update.message.text)
        await update.message.reply_text("کد تخفیف تا **چند روز دیگر** معتبر باشد؟ (برای نامحدود عدد `0` را وارد کنید):", parse_mode=ParseMode.MARKDOWN)
        return DISCOUNT_AWAIT_EXPIRY
    except ValueError:
        await update.message.reply_text("ورودی نامعتبر. لطفا یک عدد وارد کنید.")
        return DISCOUNT_AWAIT_LIMIT

async def admin_discount_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        days = int(update.message.text)
        expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S") if days > 0 else None
        d = context.user_data['new_discount']
        execute_db("INSERT INTO discount_codes (code, percentage, usage_limit, expiry_date, times_used) VALUES (?, ?, ?, ?, 0)",
                   (d['code'], d['percent'], d.get('limit', 0), expiry_date))
        await update.message.reply_text(f"\u2705 کد تخفیف `{d['code']}` با موفقیت ساخته شد.")
    except Exception as e:
        await update.message.reply_text(f"\u274C خطا در ذخیره کد تخفیف: {e}")

    context.user_data.clear()
    return await admin_discount_menu(update, context)

# --- Purchase Flow (with Discount) ---
async def start_purchase_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()

    plans = query_db("SELECT id, name, price FROM plans ORDER BY price")
    if not plans:
        await query.message.edit_text("در حال حاضر هیچ پلن فعالی برای فروش وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='start_main')]]))
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"{plan['name']} - {plan['price']:,} تومان", callback_data=f"select_plan_{plan['id']}")] for plan in plans]
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data='start_main')])

    message_data = query_db("SELECT text FROM messages WHERE message_name = 'buy_config_main'", one=True)
    text = message_data.get('text') if message_data else "لطفا پلن خود را انتخاب کنید:"

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return SELECT_PLAN

async def show_plan_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    plan_id = int(query.data.replace('select_plan_', ''))
    await query.answer()

    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)
    if not plan:
        await query.message.edit_text("خطا: پلن یافت نشد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data='buy_config_main')]]))
        return SELECT_PLAN

    context.user_data['selected_plan_id'] = plan_id
    context.user_data['original_price'] = plan['price']
    context.user_data['final_price'] = plan['price']
    context.user_data['discount_code'] = None

    traffic_display = "نامحدود" if float(plan['traffic_gb']) == 0 else f"{plan['traffic_gb']} گیگابایت"

    text = (f"شما پلن زیر را انتخاب کرده\u200cاید:\n\n"
            f"**نام پلن:** {plan['name']}\n"
            f"**توضیحات:** {plan['description']}\n"
            f"**مدت زمان:** {plan['duration_days']} روز\n"
            f"**حجم:** {traffic_display}\n"
            f"**قیمت:** {plan['price']:,} تومان\n\n"
            f"آیا تایید می\u200cکنید؟")
    keyboard = [
        [InlineKeyboardButton("\u2705 تایید و پرداخت", callback_data="confirm_purchase")],
        [InlineKeyboardButton("\U0001F381 کد تخفیف دارم", callback_data="apply_discount_start")],
        [InlineKeyboardButton("\U0001F519 بازگشت", callback_data='buy_config_main')]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return SELECT_PLAN

async def apply_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.edit_text("لطفا کد تخفیف خود را وارد کنید:")
    return AWAIT_DISCOUNT_CODE

async def receive_and_validate_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_code = update.message.text.strip().upper()
    original_price = context.user_data.get('original_price')

    if original_price is None:
        await update.message.reply_text("خطا! لطفا فرآیند را از ابتدا شروع کنید.")
        await start_command(update, context)
        return ConversationHandler.END

    code_data = query_db("SELECT * FROM discount_codes WHERE code = ?", (user_code,), one=True)
    error_message = None
    if not code_data:
        error_message = "کد تخفیف یافت نشد."
    elif code_data['expiry_date'] and datetime.strptime(code_data['expiry_date'], "%Y-%m-%d %H:%M:%S") < datetime.now():
        error_message = "این کد تخفیف منقضی شده است."
    elif code_data['usage_limit'] > 0 and code_data['times_used'] >= code_data['usage_limit']:
        error_message = "ظرفیت استفاده از این کد تخفیف به پایان رسیده است."

    current_state = RENEW_AWAIT_DISCOUNT_CODE if context.user_data.get('renewing_order_id') else AWAIT_DISCOUNT_CODE
    if error_message:
        await update.message.reply_text(f"\u274C {error_message} لطفا کد دیگری وارد کنید یا برای لغو /cancel را بفرستید.")
        return current_state

    discount_percent = code_data['percentage']
    new_price = int(original_price * (100 - discount_percent) / 100)
    context.user_data['final_price'] = new_price
    context.user_data['discount_code'] = user_code

    await update.message.reply_text(f"✅ تخفیف {discount_percent}% اعمال شد.\n"
                                  f"قیمت اصلی: {original_price:,} تومان\n"
                                  f"**قیمت جدید: {new_price:,} تومان**")

    return await show_payment_info(update, context)

async def show_payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer()

    final_price = context.user_data.get('final_price')
    if final_price is None:
        await update.effective_message.reply_text("خطا! قیمت نهایی مشخص نیست. لطفا از ابتدا شروع کنید.")
        return await cancel_flow(update, context)

    cards = query_db("SELECT card_number, holder_name FROM cards")
    payment_message_data = query_db("SELECT text FROM messages WHERE message_name = 'payment_info_text'", one=True)

    is_renewal = context.user_data.get('renewing_order_id')
    if is_renewal:
        order_id = context.user_data['renewing_order_id']
        cancel_callback = f"view_service_{order_id}"
        cancel_text = "\U0001F519 لغو تمدید"
        next_state = RENEW_AWAIT_PAYMENT
    else:
        cancel_callback = 'buy_config_main'
        cancel_text = "\U0001F519 لغو و بازگشت"
        next_state = AWAIT_PAYMENT_SCREENSHOT

    if not cards:
        text_to_send = "خطا: هیچ کارت بانکی در سیستم ثبت نشده است."
    else:
        text_to_send = payment_message_data['text'] + "\n\n"
        text_to_send += f"\U0001F4B0 **مبلغ قابل پرداخت: {final_price:,} تومان**\n\n"
        text_to_send += "\u2500" * 15 + "\n\n"
        for card in cards:
            text_to_send += f"\U0001F464 **نام دارنده:** {card['holder_name']}\n"
            text_to_send += f"\U0001F4B3 **شماره کارت:**\n`{card['card_number']}`\n\n"
        text_to_send += "\u2500" * 15

    keyboard = [[InlineKeyboardButton(cancel_text, callback_data=cancel_callback)]]

    if query:
        await query.message.edit_text(text_to_send, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text_to_send, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

    return next_state

async def receive_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    photo_file_id = update.message.photo[-1].file_id

    plan_id = context.user_data.get('selected_plan_id')
    final_price = context.user_data.get('final_price')
    discount_code = context.user_data.get('discount_code')

    if not plan_id or final_price is None:
        await update.message.reply_text("خطا: اطلاعات خرید یافت نشد. لطفا مجددا خرید کنید.")
        await start_command(update, context)
        return ConversationHandler.END

    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)
    order_id = execute_db("INSERT INTO orders (user_id, plan_id, screenshot_file_id, timestamp, final_price, discount_code) VALUES (?, ?, ?, ?, ?, ?)",
                          (user.id, plan_id, photo_file_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), final_price, discount_code))

    user_info = f"\U0001F464 **کاربر:** {user.mention_html()}\n\U0001F194 **آیدی:** `{user.id}`"
    plan_info = f"\U0001F4CB **پلن:** {plan['name']}"

    price_info = f"\U0001F4B0 **مبلغ پرداختی:** {final_price:,} تومان"
    if discount_code:
        price_info += f"\n\U0001F381 **کد تخفیف:** `{discount_code}`"

    caption = f"\U0001F514 **درخواست خرید جدید** (سفارش #{order_id})\n\n{user_info}\n\n{plan_info}\n{price_info}\n\nلطفا نتیجه را اعلام کنید:"

    keyboard = [
        [InlineKeyboardButton("\u2705 تأیید و ارسال خودکار", callback_data=f"approve_auto_{order_id}")],
        [InlineKeyboardButton("\U0001F4DD تأیید و ارسال دستی", callback_data=f"approve_manual_{order_id}")],
        [InlineKeyboardButton("\u274C رد درخواست", callback_data=f"reject_order_{order_id}")]
    ]
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
    await update.message.reply_text("\u2705 رسید شما برای ادمین ارسال شد. لطفا تا زمان تایید و دریافت کانفیگ صبور باشید.")
    context.user_data.clear()
    await start_command(update, context)
    return ConversationHandler.END

async def cancel_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.clear()
    await start_command(update, context)
    return ConversationHandler.END

# --- Generic Dynamic Button Handler ---
async def dynamic_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    RESERVED_PREFIXES = [
        'approve_', 'reject_', 'plan_', 'select_plan_', 'card_', 'msg_', 'edit_plan_',
        'btn_', 'noop_', 'renew_', 'set_', 'delete_discount_', 'add_discount_code',
        'panel_', 'backup_', 'admin_', 'apply_discount_start', 'confirm_purchase',
        'get_free_config', 'my_services', 'view_service_', 'check_join', 'buy_config_main',
        'inbound_' # New reserved prefix
    ]

    if any(query.data.startswith(p) for p in RESERVED_PREFIXES):
        logger.debug(f"Callback '{query.data}' is reserved. Skipping dynamic handler.")
        return

    await query.answer()
    message_name = query.data

    if query_db("SELECT 1 FROM messages WHERE message_name = ?", (message_name,), one=True):
        await send_dynamic_message(update, context, message_name=message_name, back_to='start_main')
    else:
        logger.warning(f"Unhandled dynamic callback_data from user {query.from_user.id}: {message_name}")
        await query.answer("این دکمه در حال حاضر کار نمی‌کند.", show_alert=True)

# --- Admin Helper ---
async def send_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("\U0001F4CB مدیریت پلن‌ها", callback_data='admin_plan_manage'), InlineKeyboardButton("\u2699\uFE0F تنظیمات", callback_data='admin_settings_manage')],
        [InlineKeyboardButton("\U0001F4C8 آمار ربات", callback_data='admin_stats'), InlineKeyboardButton("\U0001F4E4 ارسال همگانی", callback_data='admin_broadcast_menu')],
        [InlineKeyboardButton("\U0001F4DD مدیریت پیام‌ها", callback_data='admin_messages_menu'), InlineKeyboardButton("\U0001F4E8 ارسال پیام با آیدی", callback_data='admin_send_by_id_start')],
        [InlineKeyboardButton("\U0001F381 مدیریت تخفیف‌ها", callback_data='admin_discount_menu'), InlineKeyboardButton("\U0001F4BB مدیریت پنل‌ها", callback_data='admin_panels_menu')],
        [InlineKeyboardButton("\U0001F4BE دریافت بکاپ", callback_data='backup_start'), InlineKeyboardButton("\U0001F514 تست پیام یادآوری", callback_data='admin_test_reminder')],
        [InlineKeyboardButton("\u274C خروج", callback_data='admin_exit')]
    ]
    text = "\U0001F5A5\uFE0F پنل مدیریت ربات."

    if update.callback_query:
        try: await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except TelegramError: await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    return ADMIN_MAIN_MENU

# --- Admin Handlers ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    return await send_admin_panel(update, context)

async def admin_run_reminder_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("درحال اجرای دستی بررسی تمدیدها...")
    await query.message.edit_text("⏳ در حال اجرای دستی بررسی تمدیدها... این کار ممکن است کمی طول بکشد. پس از اتمام، به پنل اصلی باز خواهید گشت.")

    await check_expirations(context)

    await context.bot.send_message(ADMIN_ID, "✅ بررسی دستی تمدیدها با موفقیت انجام شد.")
    return await send_admin_panel(update, context)

# --- Order Review ---
async def admin_ask_panel_for_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    order_id = int(query.data.split('_')[-1])

    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if not order or order['status'] != 'pending':
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u26A0\uFE0F این سفارش قبلاً بررسی شده است.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    panels = query_db("SELECT id, name FROM panels ORDER BY id")
    if not panels:
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u274C **خطا:** هیچ پنلی برای ساخت کاربر تعریف نشده است.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    keyboard = [[InlineKeyboardButton(f"ساخت در: {p['name']}", callback_data=f"approve_on_panel_{order_id}_{p['id']}")] for p in panels]
    await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_approve_on_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال ساخت کانفیگ...")
    *_, order_id, panel_id = query.data.split('_')
    order_id, panel_id = int(order_id), int(panel_id)

    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    plan = query_db("SELECT * FROM plans WHERE id = ?", (order['plan_id'],), one=True)

    await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u23F3 در حال ساخت کانفیگ...", parse_mode=ParseMode.HTML, reply_markup=None)

    panel_api = VpnPanelAPI(panel_id=panel_id)
    marzban_username, config_link, message = await panel_api.create_user(order['user_id'], plan)

    if config_link and marzban_username:
        execute_db("UPDATE orders SET status = 'approved', marzban_username = ?, panel_id = ? WHERE id = ?", (marzban_username, panel_id, order_id))
        if order.get('discount_code'):
            execute_db("UPDATE discount_codes SET times_used = times_used + 1 WHERE code = ?", (order['discount_code'],))

        user_message = (f"✅ سفارش شما تایید شد!\n\n"
                        f"<b>پلن:</b> {plan['name']}\n"
                        f"لینک کانفیگ شما:\n<code>{config_link}</code>\n\n"
                        f"<b>آموزش اتصال :</b>\n"
                        f"https://t.me/madeingod_tm")
        try:
            await context.bot.send_message(order['user_id'], user_message, parse_mode=ParseMode.HTML)
            await query.message.edit_caption(caption=query.message.caption_html + f"\n\n\u2705 **ارسال خودکار موفق بود.**", parse_mode=ParseMode.HTML, reply_markup=None)
        except TelegramError as e:
            await query.message.edit_caption(caption=query.message.caption_html + f"\n\n\u26A0\uFE0F **خطا:** ارسال به کاربر ناموفق بود. {e}\nکانفیگ: <code>{config_link}</code>", parse_mode=ParseMode.HTML, reply_markup=None)
    else:
        await query.message.edit_caption(caption=query.message.caption_html + f"\n\n\u274C **خطای پنل:** `{message}`", parse_mode=ParseMode.HTML, reply_markup=None)

async def admin_review_order_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    order_id = int(query.data.split('_')[-1])
    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if not order or order['status'] != 'pending':
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u26A0\uFE0F این سفارش قبلاً بررسی شده است.", parse_mode=ParseMode.HTML, reply_markup=None)
        return
    execute_db("UPDATE orders SET status = 'rejected' WHERE id = ?", (order_id,))
    try:
        await context.bot.send_message(order['user_id'], "\u274C متاسفانه پرداخت شما تایید نشد. لطفا با پشتیبانی در تماس باشید.")
    except TelegramError: pass
    await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u274C **درخواست رد شد.**", parse_mode=ParseMode.HTML, reply_markup=None)

# --- Stateless Admin Actions (Manual Send, Send by ID) ---
async def master_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or update.effective_user.id != ADMIN_ID: return

    action = context.user_data.get('next_action')
    if not action: return

    if action == 'awaiting_manual_order_message':
        await process_manual_order_message(update, context)
    elif action == 'awaiting_user_id_for_send':
        await process_send_by_id_get_id(update, context)
    elif action == 'awaiting_message_for_user_id':
        await process_send_by_id_get_message(update, context)

    raise ApplicationHandlerStop

async def admin_manual_send_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = int(query.data.split('_')[-1])
    await query.answer()

    order = query_db("SELECT * FROM orders WHERE id = ?", (order_id,), one=True)
    if not order or order['status'] != 'pending':
        await query.message.edit_caption(caption=query.message.caption_html + "\n\n\u26A0\uFE0F این سفارش قبلاً بررسی شده است.", parse_mode=ParseMode.HTML, reply_markup=None)
        return

    context.user_data['next_action'] = 'awaiting_manual_order_message'
    context.user_data['action_data'] = {
        'order_id': order_id,
        'user_id': order['user_id'],
        'original_caption': query.message.caption_html,
        'message_id': query.message.message_id
    }

    await query.message.edit_caption(
        caption=query.message.caption_html + f"\n\n\U0001F4DD **ارسال دستی برای سفارش #{order_id}**\n"
                                             f"لطفا پیامی که میخواهید برای کاربر با آیدی `{order['user_id']}` ارسال شود را بفرستید.\n"
                                             f"پیام شما با تمام فرمت\u200cها و لینک\u200cها ارسال خواهد شد.",
        parse_mode=ParseMode.HTML
    )

async def process_manual_order_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action_data = context.user_data.get('action_data')
    if not action_data: return

    target_user_id = action_data['user_id']
    order_id = action_data['order_id']
    original_caption = action_data['original_caption']
    admin_message_id = action_data['message_id']

    try:
        await context.bot.copy_message(
            chat_id=target_user_id,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        execute_db("UPDATE orders SET status = 'approved' WHERE id = ?", (order_id,))
        if (order := query_db("SELECT discount_code FROM orders WHERE id = ?", (order_id,), one=True)) and order.get('discount_code'):
            execute_db("UPDATE discount_codes SET times_used = times_used + 1 WHERE code = ?", (order['discount_code'],))

        await update.message.reply_text(f"\u2705 پیام با موفقیت به کاربر `{target_user_id}` ارسال شد.")
        await context.bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=admin_message_id,
            caption=original_caption + f"\n\n\u2705 **ارسال دستی با موفقیت انجام شد.**",
            parse_mode=ParseMode.HTML, reply_markup=None
        )
    except TelegramError as e:
        await update.message.reply_text(f"\u274C خطا در ارسال پیام به `{target_user_id}`: {e}")

    context.user_data.pop('next_action', None)
    context.user_data.pop('action_data', None)

async def admin_send_by_id_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data['next_action'] = 'awaiting_user_id_for_send'
    await query.message.edit_text("لطفا آیدی عددی کاربر مورد نظر را ارسال کنید:")

async def process_send_by_id_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        context.user_data['next_action'] = 'awaiting_message_for_user_id'
        context.user_data['action_data'] = {'target_id': user_id}
        await update.message.reply_text(f"آیدی `{user_id}` دریافت شد. اکنون پیام خود را برای ارسال، بفرستید.")
    except ValueError:
        await update.message.reply_text("آیدی نامعتبر است. لطفا فقط عدد وارد کنید.")

async def process_send_by_id_get_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action_data = context.user_data.get('action_data')
    if not action_data: return

    user_id = action_data['target_id']
    try:
        await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        await update.message.reply_text(f"\u2705 پیام با موفقیت به کاربر `{user_id}` ارسال شد.")
    except TelegramError as e:
        await update.message.reply_text(f"\u274C خطا در ارسال پیام به `{user_id}`: {e}")

    context.user_data.pop('next_action', None)
    context.user_data.pop('action_data', None)

# --- Plan Management (Corrected Flow) ---
async def admin_plan_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_sender = None
    if update.callback_query:
        query = update.callback_query; await query.answer()
        message_sender = query.message.edit_text
    elif update.message:
        message_sender = update.message.reply_text
    if not message_sender: return ADMIN_PLAN_MENU

    plans = query_db("SELECT id, name, price FROM plans ORDER BY id")
    keyboard = []
    for p in plans:
        keyboard.append([
            InlineKeyboardButton(f"{p['name']} ({p['price']:,} ت)", callback_data=f"noop_{p['id']}"),
            InlineKeyboardButton("\u270F\uFE0F ویرایش", callback_data=f"plan_edit_{p['id']}"),
            InlineKeyboardButton("\u274C حذف", callback_data=f"plan_delete_{p['id']}")
        ])
    keyboard.append([InlineKeyboardButton("\u2795 افزودن پلن جدید", callback_data="plan_add")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")])
    await message_sender("مدیریت پلن\u200cهای فروش:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_PLAN_MENU

async def admin_plan_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    execute_db("DELETE FROM plans WHERE id=?", (plan_id,))
    await query.answer("پلن حذف شد.", show_alert=True)
    return await admin_plan_manage(update, context)

async def admin_plan_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_plan'] = {}
    await update.callback_query.message.edit_text("نام پلن جدید را وارد کنید (مثال: یک ماهه - ۳۰ گیگ):")
    return ADMIN_PLAN_AWAIT_NAME

async def admin_plan_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_plan']['name'] = update.message.text
    await update.message.reply_text("توضیحات پلن را وارد کنید (مثال: مناسب ترید و وبگردی):")
    return ADMIN_PLAN_AWAIT_DESC

async def admin_plan_receive_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_plan']['desc'] = update.message.text
    await update.message.reply_text("قیمت پلن به تومان را وارد کنید (فقط عدد):")
    return ADMIN_PLAN_AWAIT_PRICE

async def admin_plan_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['new_plan']['price'] = int(update.message.text)
        await update.message.reply_text("مدت اعتبار به روز را وارد کنید (عدد):")
        return ADMIN_PLAN_AWAIT_DAYS
    except ValueError:
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADMIN_PLAN_AWAIT_PRICE

async def admin_plan_receive_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['new_plan']['days'] = int(update.message.text)
        await update.message.reply_text("حجم به گیگابایت را وارد کنید (برای حجم نامحدود، کلمه `نامحدود` را ارسال کنید):")
        return ADMIN_PLAN_AWAIT_GIGABYTES
    except ValueError:
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADMIN_PLAN_AWAIT_DAYS
async def admin_plan_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    traffic_input = update.message.text.strip().lower()
    try:
        gb = 0.0 if traffic_input == "نامحدود" else float(traffic_input)
        context.user_data['new_plan']['gb'] = gb
        p = context.user_data['new_plan']

        execute_db("INSERT INTO plans (name, description, price, duration_days, traffic_gb) VALUES (?,?,?,?,?)",
                   (p['name'], p['desc'], p['price'], p['days'], p['gb']))

        await update.message.reply_text("\u2705 پلن با موفقیت اضافه شد.")
        context.user_data.clear()
        return await admin_plan_manage(update, context)
    except ValueError:
        await update.message.reply_text("لطفا فقط عدد (مثلا 0.5) یا کلمه `نامحدود` را وارد کنید.")
        return ADMIN_PLAN_AWAIT_GIGABYTES
    except Exception as e:
        logger.error(f"Error saving plan: {e}")
        await update.message.reply_text(f"خطا در ذخیره پلن: {e}")
        context.user_data.clear()
        return await send_admin_panel(update, context)
async def admin_plan_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    context.user_data['editing_plan_id'] = plan_id

    plan = query_db("SELECT * FROM plans WHERE id = ?", (plan_id,), one=True)
    if not plan:
        await query.answer("این پلن یافت نشد!", show_alert=True)
        return ADMIN_PLAN_MENU

    traffic_display = "نامحدود" if float(plan['traffic_gb']) == 0 else f"{plan['traffic_gb']} گیگابایت"
    text = (f"در حال ویرایش پلن **{plan['name']}**\n\n"
            f"۱. **نام:** {plan['name']}\n"
            f"۲. **توضیحات:** {plan['description']}\n"
            f"۳. **قیمت:** {plan['price']:,} تومان\n"
            f"۴. **مدت:** {plan['duration_days']} روز\n"
            f"۵. **حجم:** {traffic_display}\n\n"
            "کدام مورد را میخواهید ویرایش کنید؟")

    keyboard = [
        [InlineKeyboardButton("نام", callback_data="edit_plan_name"), InlineKeyboardButton("توضیحات", callback_data="edit_plan_description")],
        [InlineKeyboardButton("قیمت", callback_data="edit_plan_price"), InlineKeyboardButton("مدت", callback_data="edit_plan_duration_days")],
        [InlineKeyboardButton("حجم", callback_data="edit_plan_traffic_gb")],
        [InlineKeyboardButton("\U0001F519 بازگشت به لیست پلن‌ها", callback_data="admin_plan_manage")]
    ]
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_PLAN_EDIT_MENU

async def admin_plan_edit_ask_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    field = query.data.replace('edit_plan_', '')
    context.user_data['editing_plan_field'] = field

    prompts = {
        'name': "نام جدید پلن را وارد کنید:",
        'description': "توضیحات جدید را وارد کنید:",
        'price': "قیمت جدید به تومان را وارد کنید (فقط عدد):",
        'duration_days': "مدت اعتبار جدید به روز را وارد کنید (فقط عدد):",
        'traffic_gb': "حجم جدید به گیگابایت را وارد کنید (یا `نامحدود`):",
    }
    await query.message.edit_text(prompts[field])
    return ADMIN_PLAN_EDIT_AWAIT_VALUE

async def admin_plan_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    field = context.user_data.get('editing_plan_field')
    plan_id = context.user_data.get('editing_plan_id')
    new_value = update.message.text.strip()

    if not field or not plan_id:
        await update.message.reply_text("خطا! لطفا از ابتدا شروع کنید.")
        return await send_admin_panel(update, context)

    try:
        if field in ['price', 'duration_days']:
            new_value = int(new_value)
        elif field == 'traffic_gb':
            new_value = 0.0 if new_value.lower() == 'نامحدود' else float(new_value)
    except ValueError:
        await update.message.reply_text("مقدار وارد شده نامعتبر است. لطفا مجددا تلاش کنید.")
        return ADMIN_PLAN_EDIT_AWAIT_VALUE

    execute_db(f"UPDATE plans SET {field} = ? WHERE id = ?", (new_value, plan_id))
    await update.message.reply_text("\u2705 پلن با موفقیت بروزرسانی شد.")

    context.user_data.pop('editing_plan_field', None)
    fake_query = type('obj', (object,), {
        'data': f'plan_edit_{plan_id}',
        'message': update.message,
        'answer': (lambda *args, **kwargs: asyncio.sleep(0)),
        'from_user': update.effective_user
    })
    fake_update = type('obj', (object,), {'callback_query': fake_query, 'effective_user': update.effective_user})
    return await admin_plan_edit_start(fake_update, context)

# --- Settings, Cards & Panel Management ---
async def admin_settings_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    settings = {s['key']: s['value'] for s in query_db("SELECT key, value FROM settings")}
    trial_status = settings.get('free_trial_status', '0')
    trial_button_text = "\u274C غیرفعال کردن تست" if trial_status == '1' else "\u2705 فعال کردن تست"
    trial_button_callback = "set_trial_status_0" if trial_status == '1' else "set_trial_status_1"

    text = (f"\u2699\uFE0F **تنظیمات کلی ربات**\n\n"
            f"**وضعیت تست:** {'فعال' if trial_status == '1' else 'غیرفعال'}\n"
            f"**روز تست:** `{settings.get('free_trial_days', '1')}` | **حجم تست:** `{settings.get('free_trial_gb', '0.2')} GB`")
    keyboard = [
        [InlineKeyboardButton(trial_button_text, callback_data=trial_button_callback)],
        [InlineKeyboardButton("روز/حجم تست", callback_data="set_trial_days"), InlineKeyboardButton("ویرایش متن پرداخت", callback_data="set_payment_text")],
        [InlineKeyboardButton("\U0001F4B3 مدیریت کارت\u200cها", callback_data="admin_cards_menu")],
        [InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")]
    ]
    await query.message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    return SETTINGS_MENU

async def admin_toggle_trial_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    new_status = query.data.split('_')[-1]
    execute_db("UPDATE settings SET value = ? WHERE key = 'free_trial_status'", (new_status,))
    await query.answer(f"وضعیت تست رایگان {'فعال' if new_status == '1' else 'غیرفعال'} شد.", show_alert=True)
    return await admin_settings_manage(update, context)

async def admin_cards_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_sender = None
    if update.callback_query:
        query = update.callback_query; await query.answer()
        message_sender = query.message.edit_text
    elif update.message:
        message_sender = update.message.reply_text
    if not message_sender: return ADMIN_CARDS_MENU

    cards = query_db("SELECT id, card_number, holder_name FROM cards")
    keyboard = []
    text = "\U0001F4B3 **مدیریت کارت\u200cهای بانکی**\n\n"
    if cards:
        text += "لیست کارت\u200cهای فعلی:"
        for card in cards:
            keyboard.append([InlineKeyboardButton(f"{card['card_number']}", callback_data=f"noop_{card['id']}"), InlineKeyboardButton("\u274C حذف", callback_data=f"card_delete_{card['id']}")])
    else: text += "هیچ کارتی ثبت نشده است."
    keyboard.append([InlineKeyboardButton("\u2795 افزودن کارت جدید", callback_data="card_add_start")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت به تنظیمات", callback_data="admin_settings_manage")])
    await message_sender(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_CARDS_MENU

async def admin_card_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    card_id = int(query.data.split('_')[-1])
    execute_db("DELETE FROM cards WHERE id = ?", (card_id,))
    await query.answer("کارت با موفقیت حذف شد.", show_alert=True)
    return await admin_cards_menu(update, context)

async def admin_card_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; context.user_data['new_card'] = {}
    await query.message.edit_text("لطفا **شماره کارت** ۱۶ رقمی را وارد کنید:")
    return ADMIN_CARDS_AWAIT_NUMBER

async def admin_card_add_receive_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_card']['number'] = update.message.text
    await update.message.reply_text("لطفا **نام و نام خانوادگی** صاحب کارت را وارد کنید:")
    return ADMIN_CARDS_AWAIT_HOLDER

async def admin_card_add_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    card_number = context.user_data['new_card']['number']
    holder_name = update.message.text
    execute_db("INSERT INTO cards (card_number, holder_name) VALUES (?, ?)", (card_number, holder_name))
    await update.message.reply_text("\u2705 کارت جدید با موفقیت ثبت شد.")
    context.user_data.clear()
    return await admin_cards_menu(update, context)

async def admin_settings_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    action = query.data
    prompts = {
        'set_trial_days': "روز و حجم جدید تست را با فرمت `روز-حجم` وارد کنید (مثال: 1-0.5):",
        'set_payment_text': "متن جدید برای صفحه پرداخت را وارد کنید:"
    }
    states = {
        'set_trial_days': SETTINGS_AWAIT_TRIAL_DAYS,
        'set_payment_text': SETTINGS_AWAIT_PAYMENT_TEXT
    }
    await query.message.edit_text(prompts[action])
    return states[action]

async def admin_settings_save_trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        days, gb = update.message.text.split('-')
        execute_db("UPDATE settings SET value = ? WHERE key = 'free_trial_days'", (days.strip(),))
        execute_db("UPDATE settings SET value = ? WHERE key = 'free_trial_gb'", (gb.strip(),))
        await update.message.reply_text("\u2705 تنظیمات تست رایگان با موفقیت ذخیره شد.")
    except Exception:
        await update.message.reply_text("فرمت نامعتبر است. لطفا با فرمت `روز-حجم` وارد کنید.")
        return SETTINGS_AWAIT_TRIAL_DAYS
    return await send_admin_panel(update, context)

async def admin_settings_save_payment_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_text = update.message.text
    execute_db("UPDATE messages SET text = ? WHERE message_name = ?", (new_text, 'payment_info_text'))
    await update.message.reply_text("\u2705 متن پرداخت با موفقیت ذخیره شد.")
    return await send_admin_panel(update, context)

# --- Panel Management (with Inbound Editor) ---
async def admin_panels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer()

    panels = query_db("SELECT id, name, url FROM panels ORDER BY id")
    keyboard = []
    text = "\U0001F4BB **مدیریت پنل‌های مرزبان**\n\n"
    if panels:
        for p in panels:
            keyboard.append([
                InlineKeyboardButton(f"{p['name']}", callback_data=f"noop_{p['id']}"),
                InlineKeyboardButton(" اینباندها", callback_data=f"panel_inbounds_{p['id']}"),
                InlineKeyboardButton("\u274C حذف", callback_data=f"panel_delete_{p['id']}")
            ])
    else:
        text += "هیچ پنلی ثبت نشده است."

    keyboard.append([InlineKeyboardButton("\u2795 افزودن پنل جدید", callback_data="panel_add_start")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت به پنل اصلی", callback_data="admin_main")])

    sender = query.message.edit_text if query else update.message.reply_text
    await sender(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_PANELS_MENU

async def admin_panel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    panel_id = int(query.data.split('_')[-1])
    # Deletion will cascade to panel_inbounds table
    execute_db("DELETE FROM panels WHERE id=?", (panel_id,))
    await query.answer("پنل و اینباندهای مرتبط با آن حذف شدند.", show_alert=True)
    return await admin_panels_menu(update, context)

async def admin_panel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel'] = {}
    await update.callback_query.message.edit_text("نام پنل را وارد کنید (مثال: پنل آلمان):")
    return ADMIN_PANEL_AWAIT_NAME

async def admin_panel_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['name'] = update.message.text
    await update.message.reply_text("آدرس کامل (URL) پنل را وارد کنید (مثال: https://panel.example.com):")
    return ADMIN_PANEL_AWAIT_URL

async def admin_panel_receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['url'] = update.message.text
    await update.message.reply_text("نام کاربری (username) ادمین پنل را وارد کنید:")
    return ADMIN_PANEL_AWAIT_USER

async def admin_panel_receive_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['user'] = update.message.text
    await update.message.reply_text("رمز عبور (password) ادمین پنل را وارد کنید:")
    return ADMIN_PANEL_AWAIT_PASS

async def admin_panel_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['pass'] = update.message.text
    p = context.user_data['new_panel']
    try:
        execute_db("INSERT INTO panels (name, url, username, password) VALUES (?,?,?,?)",
                   (p['name'], p['url'], p['user'], p['pass']))
        await update.message.reply_text("\u2705 پنل با موفقیت اضافه شد.")
        context.user_data.clear()
        return await admin_panels_menu(update, context)
    except sqlite3.IntegrityError:
        await update.message.reply_text("خطا: نام پنل تکراری است. لطفا نام دیگری انتخاب کنید.")
        context.user_data.clear()
        return ADMIN_PANEL_AWAIT_NAME
    except Exception as e:
        await update.message.reply_text(f"خطا در ذخیره‌سازی: {e}")
        context.user_data.clear()
        return await send_admin_panel(update, context)

# --- NEW: Inbound Management Handlers ---
async def admin_panel_inbounds_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if 'panel_inbounds_' in query.data:
        panel_id = int(query.data.split('_')[-1])
        context.user_data['editing_panel_id_for_inbounds'] = panel_id
    else:
        panel_id = context.user_data.get('editing_panel_id_for_inbounds')

    if not panel_id:
        await query.message.edit_text("خطا: آیدی پنل یافت نشد. لطفا دوباره تلاش کنید.")
        return ADMIN_PANELS_MENU

    await query.answer()

    panel = query_db("SELECT name FROM panels WHERE id = ?", (panel_id,), one=True)
    inbounds = query_db("SELECT id, protocol, tag FROM panel_inbounds WHERE panel_id = ? ORDER BY id", (panel_id,))

    text = f" **مدیریت اینباندهای پنل: {panel['name']}**\n\n"
    keyboard = []

    if not inbounds:
        text += "هیچ اینباندی برای این پنل تنظیم نشده است."
    else:
        text += "لیست اینباندها (پروتکل: تگ):\n"
        for i in inbounds:
            keyboard.append([
                InlineKeyboardButton(f"{i['protocol']}: {i['tag']}", callback_data=f"noop_{i['id']}"),
                InlineKeyboardButton("\u274C حذف", callback_data=f"inbound_delete_{i['id']}")
            ])

    keyboard.append([InlineKeyboardButton("\u2795 افزودن اینباند جدید", callback_data="inbound_add_start")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت به لیست پنل‌ها", callback_data="admin_panels_menu")])

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_PANEL_INBOUNDS_MENU

async def admin_panel_inbound_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    inbound_id = int(query.data.split('_')[-1])
    execute_db("DELETE FROM panel_inbounds WHERE id = ?", (inbound_id,))
    await query.answer("اینباند با موفقیت حذف شد.", show_alert=True)
    return await admin_panel_inbounds_menu(update, context)

async def admin_panel_inbound_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data['new_inbound'] = {}
    await query.message.edit_text("لطفا **پروتکل** اینباند را وارد کنید (مثلا `vless`, `vmess`, `trojan`):")
    return ADMIN_PANEL_INBOUNDS_AWAIT_PROTOCOL

async def admin_panel_inbound_receive_protocol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_inbound']['protocol'] = update.message.text.strip().lower()
    await update.message.reply_text("بسیار خب. حالا **تگ (tag)** دقیق اینباند را وارد کنید:")
    return ADMIN_PANEL_INBOUNDS_AWAIT_TAG

async def admin_panel_inbound_receive_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    panel_id = context.user_data.get('editing_panel_id_for_inbounds')
    if not panel_id:
        await update.message.reply_text("خطا: آیدی پنل یافت نشد. لطفا دوباره تلاش کنید.")
        return await admin_panels_menu(update, context)

    protocol = context.user_data['new_inbound']['protocol']
    tag = update.message.text.strip()

    try:
        execute_db("INSERT INTO panel_inbounds (panel_id, protocol, tag) VALUES (?, ?, ?)", (panel_id, protocol, tag))
        await update.message.reply_text("✅ اینباند با موفقیت اضافه شد.")
    except sqlite3.IntegrityError:
        await update.message.reply_text("❌ خطا: این تگ قبلا برای این پنل ثبت شده است.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ذخیره‌سازی: {e}")

    context.user_data.pop('new_inbound', None)

    # Fake update to show the menu again
    fake_query = type('obj', (object,), { 'data': f"panel_inbounds_{panel_id}", 'message': update.message, 'answer': lambda: asyncio.sleep(0) })
    fake_update = type('obj', (object,), {'callback_query': fake_query})
    return await admin_panel_inbounds_menu(fake_update, context)

# --- Message and Button Editor ---
async def admin_messages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    messages = query_db("SELECT message_name FROM messages")
    keyboard = [[InlineKeyboardButton(m['message_name'], callback_data=f"msg_select_{m['message_name']}")] for m in messages]
    keyboard.append([InlineKeyboardButton("\u2795 افزودن پیام جدید", callback_data="msg_add_start")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")])
    await query.message.edit_text("مدیریت پیام‌ها و صفحات:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MESSAGES_MENU

async def msg_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.edit_text("نام انگلیسی و منحصر به فرد برای پیام جدید وارد کنید (مثال: `about_us`):")
    return ADMIN_MESSAGES_ADD_AWAIT_NAME

async def msg_add_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_name = update.message.text.strip()
    if not message_name.isascii() or ' ' in message_name:
        await update.message.reply_text("خطا: نام باید انگلیسی و بدون فاصله باشد.")
        return ADMIN_MESSAGES_ADD_AWAIT_NAME
    if query_db("SELECT 1 FROM messages WHERE message_name = ?", (message_name,), one=True):
        await update.message.reply_text("خطا: این نام قبلا استفاده شده است.")
        return ADMIN_MESSAGES_ADD_AWAIT_NAME
    context.user_data['new_message_name'] = message_name
    await update.message.reply_text("محتوای این پیام (متن یا عکس) را ارسال کنید.")
    return ADMIN_MESSAGES_ADD_AWAIT_CONTENT

async def msg_add_receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_name = context.user_data.get('new_message_name')
    if not message_name: return await send_admin_panel(update, context)
    text = update.message.text or update.message.caption
    file_id, file_type = None, None
    if update.message.photo: file_id, file_type = update.message.photo[-1].file_id, 'photo'
    elif update.message.video: file_id, file_type = update.message.video.file_id, 'video'
    elif update.message.document: file_id, file_type = update.message.document.file_id, 'document'
    execute_db("INSERT INTO messages (message_name, text, file_id, file_type) VALUES (?, ?, ?, ?)", (message_name, text, file_id, file_type))
    await update.message.reply_text(f"\u2705 پیام جدید با نام `{message_name}` ساخته شد.")
    context.user_data.clear()
    return await send_admin_panel(update, context)

async def admin_messages_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message_name = query.data.replace("msg_select_", "")
    context.user_data['editing_message_name'] = message_name
    await query.answer()
    message_data = query_db("SELECT text FROM messages WHERE message_name = ?", (message_name,), one=True)
    text_preview = (message_data['text'][:200] + '...') if message_data and message_data.get('text') and len(message_data['text']) > 200 else (message_data.get('text') if message_data else 'متن خالی')
    text = f"**در حال ویرایش:** `{message_name}`\n\n**پیش‌نمایش متن:**\n{text_preview}\n\nچه کاری می‌خواهید انجام دهید؟"
    keyboard = [
        [InlineKeyboardButton("\U0001F4DD ویرایش متن", callback_data="msg_action_edit_text")],
        [InlineKeyboardButton("\U0001F518 ویرایش دکمه‌ها", callback_data="msg_action_edit_buttons")],
        [InlineKeyboardButton("\U0001F519 بازگشت به لیست", callback_data="admin_messages_menu")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MESSAGES_SELECT

async def admin_messages_edit_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message_name = context.user_data['editing_message_name']
    await query.message.edit_text(f"لطفا متن جدید برای پیام `{message_name}` را ارسال کنید.", parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MESSAGES_EDIT_TEXT

async def admin_messages_edit_text_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_name = context.user_data['editing_message_name']
    new_text = update.message.text
    execute_db("UPDATE messages SET text = ? WHERE message_name = ?", (new_text, message_name))
    await update.message.reply_text("\u2705 متن با موفقیت بروزرسانی شد.")
    context.user_data.clear()
    return await send_admin_panel(update, context)

async def admin_buttons_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    message_name = context.user_data.get('editing_message_name')
    if not message_name: return ADMIN_MAIN_MENU
    buttons = query_db("SELECT id, text FROM buttons WHERE menu_name = ? ORDER BY row, col", (message_name,))
    keyboard = []
    if buttons:
        for b in buttons:
            keyboard.append([InlineKeyboardButton(f"{b['text']}", callback_data=f"noop_{b['id']}"), InlineKeyboardButton("\u274C حذف", callback_data=f"btn_delete_{b['id']}")])
    keyboard.append([InlineKeyboardButton("\u2795 افزودن دکمه جدید", callback_data="btn_add_new")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data=f"msg_select_{message_name}")])
    await query.message.edit_text(f"ویرایش دکمه‌های پیام `{message_name}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MESSAGES_SELECT

async def admin_button_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    button_id = int(query.data.replace("btn_delete_", ""))
    execute_db("DELETE FROM buttons WHERE id = ?", (button_id,))
    await query.answer("دکمه حذف شد.", show_alert=True)
    return await admin_buttons_menu(update, context)

async def admin_button_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data['new_button'] = {'menu_name': context.user_data['editing_message_name']}
    await query.message.edit_text("لطفا متن دکمه جدید را وارد کنید:")
    return ADMIN_BUTTON_ADD_AWAIT_TEXT

async def admin_button_add_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_button']['text'] = update.message.text
    await update.message.reply_text("لطفا **دیتای بازگشتی** (callback_data) یا **لینک URL** را وارد کنید:")
    return ADMIN_BUTTON_ADD_AWAIT_TARGET

async def admin_button_add_receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_button']['target'] = update.message.text
    await update.message.reply_text("آیا این یک لینک URL است؟", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("بله، URL است", callback_data="btn_isurl_1")],
        [InlineKeyboardButton("خیر، دیتا است", callback_data="btn_isurl_0")]]))
    return ADMIN_BUTTON_ADD_AWAIT_URL

async def admin_button_add_receive_is_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data['new_button']['is_url'] = int(query.data.replace("btn_isurl_", ""))
    await query.message.edit_text("لطفا شماره **سطر** (row) را وارد کنید (شروع از 1):")
    return ADMIN_BUTTON_ADD_AWAIT_ROW

async def admin_button_add_receive_row(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['new_button']['row'] = int(update.message.text)
        await update.message.reply_text("لطفا شماره **ستون** (column) را وارد کنید (شروع از 1):")
        return ADMIN_BUTTON_ADD_AWAIT_COL
    except ValueError:
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADMIN_BUTTON_ADD_AWAIT_ROW

async def admin_button_add_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data['new_button']['col'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text("لطفا فقط عدد وارد کنید.")
        return ADMIN_BUTTON_ADD_AWAIT_COL
    b = context.user_data['new_button']
    execute_db("INSERT INTO buttons (menu_name, text, target, is_url, row, col) VALUES (?, ?, ?, ?, ?, ?)",
               (b['menu_name'], b['text'], b['target'], b['is_url'], b['row'], b['col']))
    await update.message.reply_text("\u2705 دکمه با موفقیت اضافه شد.")
    return await admin_buttons_menu(update, context)

# --- Broadcast Feature ---
async def admin_broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    keyboard = [
        [InlineKeyboardButton("ارسال به همه کاربران", callback_data="broadcast_all")],
        [InlineKeyboardButton("ارسال به خریداران", callback_data="broadcast_buyers")],
        [InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")]
    ]
    await query.message.edit_text("پیام خود را به کدام گروه از کاربران می‌خواهید ارسال کنید؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return BROADCAST_SELECT_AUDIENCE

async def admin_broadcast_ask_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    context.user_data['broadcast_audience'] = query.data.split('_')[-1]
    await query.message.edit_text("لطفا پیام خود را برای ارسال، در قالب متن یا عکس ارسال کنید. (برای لغو /cancel را بفرستید)")
    return BROADCAST_AWAIT_MESSAGE

async def admin_broadcast_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    audience = context.user_data.get('broadcast_audience')
    if not audience: return await send_admin_panel(update, context)

    await update.message.reply_text("درحال آماده سازی برای ارسال...")
    if audience == 'all':
        users = query_db("SELECT user_id FROM users WHERE user_id != ?", (ADMIN_ID,))
    else:
        users = query_db("SELECT DISTINCT user_id FROM orders WHERE status = 'approved' AND user_id != ?", (ADMIN_ID,))
    if not users:
        await update.message.reply_text("هیچ کاربری در گروه هدف یافت نشد.")
        return await send_admin_panel(update, context)

    user_ids = [user['user_id'] for user in users]
    successful_sends, failed_sends = 0, 0
    await context.bot.send_message(ADMIN_ID, f"شروع ارسال پیام همگانی به {len(user_ids)} کاربر...")
    for user_id in user_ids:
        try:
            await context.bot.copy_message(chat_id=user_id, from_chat_id=update.message.chat_id, message_id=update.message.message_id)
            successful_sends += 1
        except (Forbidden, BadRequest): failed_sends += 1
        except Exception: failed_sends += 1
        await asyncio.sleep(0.1)
    report_text = f"\u2705 **گزارش ارسال همگانی** \u2705\n\nتعداد کل هدف: {len(user_ids)}\nارسال موفق: {successful_sends}\nارسال ناموفق: {failed_sends}"
    await context.bot.send_message(ADMIN_ID, report_text)
    context.user_data.clear()
    return await send_admin_panel(update, context)

# --- Stats ---
async def admin_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    total_users = query_db("SELECT COUNT(user_id) as c FROM users", one=True)['c']
    trial_users = query_db("SELECT COUNT(user_id) as c FROM free_trials", one=True)['c']
    purchased_users = query_db("SELECT COUNT(DISTINCT user_id) as c FROM orders WHERE status = 'approved'", one=True)['c']
    text = (f"\U0001F4C8 **آمار ربات**\n\n"
            f"\U0001F465 **کل کاربران:** {total_users} نفر\n"
            f"\U0001F4B8 **تعداد خریداران:** {purchased_users} نفر\n"
            f"\U0001F3AB **دریافت کنندگان تست:** {trial_users} نفر")
    keyboard = [
        [InlineKeyboardButton("\U0001F504 بررسی کاربران فعال", callback_data="stats_refresh")],
        [InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")]]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_STATS_MENU

async def admin_stats_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.edit_text("\U0001F55C در حال بررسی کاربران... این عملیات ممکن است کمی طول بکشد.")

    all_users = query_db("SELECT user_id FROM users WHERE user_id != ?", (ADMIN_ID,))
    if not all_users: return await admin_stats_menu(update, context)

    inactive_count, inactive_ids = 0, []
    for user in all_users:
        user_id = user['user_id']
        try:
            await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
        except (Forbidden, BadRequest):
            inactive_count += 1
            inactive_ids.append(user_id)
        await asyncio.sleep(0.1)

    if inactive_ids:
        placeholders = ','.join('?' for _ in inactive_ids)
        execute_db(f"DELETE FROM users WHERE user_id IN ({placeholders})", inactive_ids)
        execute_db(f"DELETE FROM free_trials WHERE user_id IN ({placeholders})", inactive_ids)
        logger.info(f"Removed {inactive_count} inactive users.")

    await query.answer(f"{inactive_count} کاربر غیرفعال حذف شدند.", show_alert=True)
    return await admin_stats_menu(update, context)

# --- Backup Feature ---
async def backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    panels = query_db("SELECT id, name FROM panels")
    if not panels:
        await query.message.edit_text("هیچ پنلی برای بکاپ‌گیری وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")]]))
        return ADMIN_MAIN_MENU

    keyboard = [[InlineKeyboardButton(f"بکاپ از پنل: {p['name']}", callback_data=f"backup_panel_{p['id']}")] for p in panels]
    if len(panels) > 1:
        keyboard.insert(0, [InlineKeyboardButton("بکاپ از همه پنل‌ها", callback_data="backup_panel_all")])
    keyboard.append([InlineKeyboardButton("\U0001F519 بازگشت", callback_data="admin_main")])
    await query.message.edit_text("لطفا پنل مورد نظر برای تهیه بکاپ را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return BACKUP_CHOOSE_PANEL

async def admin_generate_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.edit_text("در حال آماده سازی بکاپ... لطفا صبر کنید.")

    target = query.data.split('_')[-1]
    panel_ids = [p['id'] for p in query_db("SELECT id FROM panels")] if target == 'all' else [int(target)]

    if not panel_ids:
        await query.message.edit_text("خطا: پنلی برای بکاپ‌گیری یافت نشد.")
        return await send_admin_panel(update, context)

    output = io.StringIO()
    csv_writer = csv.writer(output)
    header = ['Panel Name', 'Marzban Username', 'Expire Date', 'Data Limit (GB)', 'Used Traffic (GB)', 'Subscription Link']
    csv_writer.writerow(header)
    row_count = 0

    for panel_id in panel_ids:
        try:
            panel_info = query_db("SELECT name, url FROM panels WHERE id = ?", (panel_id,), one=True)
            panel_api = VpnPanelAPI(panel_id=panel_id)
            users, msg = await panel_api.get_all_users()
            if not users:
                logger.warning(f"Could not get users from panel {panel_info['name']}: {msg}")
                continue

            for user in users:
                expire_date = "N/A" if not user.get('expire') else datetime.fromtimestamp(user['expire']).strftime('%Y-%m-%d')
                data_limit_gb = "Unlimited" if user.get('data_limit', 0) == 0 else bytes_to_gb(user['data_limit'])
                used_traffic_gb = bytes_to_gb(user.get('used_traffic', 0))
                sub_url = (f"{panel_api.base_url}{user['subscription_url']}") if user.get('subscription_url') and not user['subscription_url'].startswith('http') else user.get('subscription_url', 'N/A')

                csv_writer.writerow([panel_info['name'], user['username'], expire_date, data_limit_gb, used_traffic_gb, sub_url])
                row_count += 1
        except Exception as e:
            logger.error(f"Error processing backup for panel ID {panel_id}: {e}")
            continue

    if row_count == 0:
         await query.message.edit_text("هیچ کاربری در پنل(های) انتخاب شده برای بکاپ یافت نشد.")
    else:
        output.seek(0)
        file_to_send = InputFile(io.BytesIO(output.getvalue().encode('utf-8')), filename=f"marzban_backup_{datetime.now().strftime('%Y-%m-%d')}.csv")
        await context.bot.send_document(chat_id=ADMIN_ID, document=file_to_send, caption=f"✅ بکاپ با موفقیت از {row_count} کاربر تهیه شد.")
        await query.message.delete()

    return await send_admin_panel(update, context)


# --- Renewal Reminder Job ---
async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running daily expiration check job...")
    today_str = datetime.now().strftime('%Y-%m-%d')
    reminder_msg_data = query_db("SELECT text FROM messages WHERE message_name = 'renewal_reminder_text'", one=True)
    if not reminder_msg_data:
        logger.error("Renewal reminder message template not found in DB. Skipping job.")
        return
    reminder_msg_template = reminder_msg_data['text']

    active_orders = query_db(
        "SELECT id, user_id, marzban_username, panel_id, last_reminder_date FROM orders "
        "WHERE status = 'approved' AND marzban_username IS NOT NULL AND panel_id IS NOT NULL"
    )

    orders_map = {}
    for order in active_orders:
        if order['marzban_username'] not in orders_map:
             orders_map[order['marzban_username']] = []
        orders_map[order['marzban_username']].append(order)

    all_panels = query_db("SELECT id FROM panels")
    for panel_data in all_panels:
        try:
            panel_api = VpnPanelAPI(panel_id=panel_data['id'])
            all_users, msg = await panel_api.get_all_users()
            if not all_users:
                logger.warning(f"Skipping panel ID {panel_data['id']} due to get_all_users error: {msg}")
                continue

            for m_user in all_users:
                username = m_user.get('username')
                if username not in orders_map: continue

                user_orders = orders_map[username]
                for order in user_orders:
                    if order['last_reminder_date'] == today_str: continue

                    details_str = ""
                    # Time-based check
                    if m_user.get('expire'):
                        expire_dt = datetime.fromtimestamp(m_user['expire'])
                        days_left = (expire_dt - datetime.now()).days
                        if 0 <= days_left <= 3:
                            details_str = f"تنها **{days_left+1} روز** تا پایان اعتبار زمانی سرویس شما باقی مانده است."

                    # Usage-based check
                    if not details_str and m_user.get('data_limit', 0) > 0:
                        usage_percent = (m_user.get('used_traffic', 0) / m_user['data_limit']) * 100
                        if usage_percent >= 80:
                           details_str = f"بیش از **{int(usage_percent)} درصد** از حجم سرویس شما مصرف شده است."

                    if details_str:
                        try:
                            final_msg = reminder_msg_template.format(marzban_username=username, details=details_str)
                            await context.bot.send_message(order['user_id'], final_msg, parse_mode=ParseMode.MARKDOWN)
                            execute_db("UPDATE orders SET last_reminder_date = ? WHERE id = ?", (today_str, order['id']))
                            logger.info(f"Sent reminder to user {order['user_id']} for service {username}")
                        except (Forbidden, BadRequest):
                            logger.warning(f"Could not send reminder to blocked user {order['user_id']}")
                        except Exception as e:
                            logger.error(f"Error sending reminder to {order['user_id']}: {e}")
                        await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to process reminders for panel ID {panel_data['id']}: {e}")

# --- Fallback handlers ---
async def cancel_admin_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("عملیات لغو شد.")
    return await send_admin_panel(update, context)

async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    await query.message.edit_text("از پنل خارج شدید.")
    return ConversationHandler.END

# --- Main Function ---
def main() -> None:
    db_setup()
    application = Application.builder().token(BOT_TOKEN).build()

    if application.job_queue:
        application.job_queue.run_daily(check_expirations, time=time(hour=9, minute=0, second=0), name="daily_expiration_check")

    application.add_handler(TypeHandler(Update, force_join_checker), group=-1)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, master_message_handler), group=0)

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_command)],
        states={
            ADMIN_MAIN_MENU: [
                CallbackQueryHandler(admin_plan_manage, pattern='^admin_plan_manage$'),
                CallbackQueryHandler(admin_settings_manage, pattern='^admin_settings_manage$'),
                CallbackQueryHandler(admin_stats_menu, pattern='^admin_stats$'),
                CallbackQueryHandler(admin_messages_menu, pattern='^admin_messages_menu$'),
                CallbackQueryHandler(admin_broadcast_menu, pattern='^admin_broadcast_menu$'),
                CallbackQueryHandler(admin_send_by_id_start, pattern='^admin_send_by_id_start$'),
                CallbackQueryHandler(admin_discount_menu, pattern='^admin_discount_menu$'),
                CallbackQueryHandler(admin_panels_menu, pattern='^admin_panels_menu$'),
                CallbackQueryHandler(backup_start, pattern='^backup_start$'),
                CallbackQueryHandler(admin_run_reminder_check, pattern=r'^admin_test_reminder$')
            ],
            ADMIN_PLAN_MENU: [
                CallbackQueryHandler(admin_plan_delete, pattern=r'^plan_delete_\d+$'),
                CallbackQueryHandler(admin_plan_edit_start, pattern=r'^plan_edit_\d+$'),
                CallbackQueryHandler(admin_plan_add_start, pattern='^plan_add$'),
                CallbackQueryHandler(admin_command, pattern='^admin_main$'),
            ],
            ADMIN_PLAN_AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_receive_name)],
            ADMIN_PLAN_AWAIT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_receive_desc)],
            ADMIN_PLAN_AWAIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_receive_price)],
            ADMIN_PLAN_AWAIT_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_receive_days)],
            ADMIN_PLAN_AWAIT_GIGABYTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_save)],
            ADMIN_PLAN_EDIT_MENU: [
                CallbackQueryHandler(admin_plan_edit_ask_value, pattern=r'^edit_plan_'),
                CallbackQueryHandler(admin_plan_manage, pattern='^admin_plan_manage$')
            ],
            ADMIN_PLAN_EDIT_AWAIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_plan_edit_save)],
            SETTINGS_MENU: [
                CallbackQueryHandler(admin_settings_ask, pattern=r'^set_(trial_days|payment_text)$'),
                CallbackQueryHandler(admin_toggle_trial_status, pattern=r'^set_trial_status_(0|1)$'),
                CallbackQueryHandler(admin_cards_menu, pattern='^admin_cards_menu$'),
                CallbackQueryHandler(admin_command, pattern='^admin_main$'),
            ],
            ADMIN_CARDS_MENU: [
                CallbackQueryHandler(admin_card_add_start, pattern='^card_add_start$'),
                CallbackQueryHandler(admin_card_delete, pattern=r'^card_delete_'),
                CallbackQueryHandler(admin_settings_manage, pattern='^admin_settings_manage$'),
            ],
            ADMIN_CARDS_AWAIT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_card_add_receive_number)],
            ADMIN_CARDS_AWAIT_HOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_card_add_save)],
            SETTINGS_AWAIT_TRIAL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings_save_trial)],
            SETTINGS_AWAIT_PAYMENT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_settings_save_payment_text)],
            ADMIN_PANELS_MENU: [
                CallbackQueryHandler(admin_panel_add_start, pattern='^panel_add_start$'),
                CallbackQueryHandler(admin_panel_delete, pattern=r'^panel_delete_'),
                CallbackQueryHandler(admin_panel_inbounds_menu, pattern=r'^panel_inbounds_'), # New
                CallbackQueryHandler(admin_command, pattern='^admin_main$'),
            ],
            ADMIN_PANEL_AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_receive_name)],
            ADMIN_PANEL_AWAIT_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_receive_url)],
            ADMIN_PANEL_AWAIT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_receive_user)],
            ADMIN_PANEL_AWAIT_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_save)],
            # New states for inbound management
            ADMIN_PANEL_INBOUNDS_MENU: [
                CallbackQueryHandler(admin_panel_inbound_add_start, pattern='^inbound_add_start$'),
                CallbackQueryHandler(admin_panel_inbound_delete, pattern=r'^inbound_delete_'),
                CallbackQueryHandler(admin_panels_menu, pattern='^admin_panels_menu$'),
            ],
            ADMIN_PANEL_INBOUNDS_AWAIT_PROTOCOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_inbound_receive_protocol)],
            ADMIN_PANEL_INBOUNDS_AWAIT_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_inbound_receive_tag)],
            ADMIN_MESSAGES_MENU: [
                CallbackQueryHandler(admin_messages_select, pattern='^msg_select_'),
                CallbackQueryHandler(msg_add_start, pattern='^msg_add_start$'),
                CallbackQueryHandler(admin_command, pattern='^admin_main$'),
            ],
            ADMIN_MESSAGES_ADD_AWAIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, msg_add_receive_name)],
            ADMIN_MESSAGES_ADD_AWAIT_CONTENT: [MessageHandler(filters.ALL & ~filters.COMMAND, msg_add_receive_content)],
            ADMIN_MESSAGES_SELECT: [
                CallbackQueryHandler(admin_messages_edit_text_start, pattern='^msg_action_edit_text$'),
                CallbackQueryHandler(admin_buttons_menu, pattern='^msg_action_edit_buttons$'),
                CallbackQueryHandler(admin_button_delete, pattern=r'^btn_delete_'),
                CallbackQueryHandler(admin_button_add_start, pattern=r'^btn_add_new$'),
                CallbackQueryHandler(admin_messages_menu, pattern='^admin_messages_menu$'),
            ],
            ADMIN_MESSAGES_EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_messages_edit_text_save)],
            ADMIN_BUTTON_ADD_AWAIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_add_receive_text)],
            ADMIN_BUTTON_ADD_AWAIT_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_add_receive_target)],
            ADMIN_BUTTON_ADD_AWAIT_URL: [CallbackQueryHandler(admin_button_add_receive_is_url, pattern='^btn_isurl_')],
            ADMIN_BUTTON_ADD_AWAIT_ROW: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_add_receive_row)],
            ADMIN_BUTTON_ADD_AWAIT_COL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_button_add_save)],
            BROADCAST_SELECT_AUDIENCE: [CallbackQueryHandler(admin_broadcast_ask_message, pattern='^broadcast_(all|buyers)$')],
            BROADCAST_AWAIT_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_broadcast_execute)],
            DISCOUNT_MENU: [
                CallbackQueryHandler(admin_discount_add_start, pattern='^add_discount_code$'),
                CallbackQueryHandler(admin_discount_delete, pattern=r'^delete_discount_\d+$'),
                CallbackQueryHandler(admin_command, pattern='^admin_main$'),
            ],
            DISCOUNT_AWAIT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_discount_receive_code)],
            DISCOUNT_AWAIT_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_discount_receive_percent)],
            DISCOUNT_AWAIT_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_discount_receive_limit)],
            DISCOUNT_AWAIT_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_discount_save)],
            BACKUP_CHOOSE_PANEL: [CallbackQueryHandler(admin_generate_backup, pattern=r'^backup_panel_')],
        },
        fallbacks=[CommandHandler('cancel', cancel_admin_conversation), CallbackQueryHandler(exit_admin_panel, pattern='^admin_exit$'), CallbackQueryHandler(admin_command, pattern='^admin_main$')],
        allow_reentry=True,
    )

    purchase_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_purchase_flow, pattern='^buy_config_main$')],
        states={
            SELECT_PLAN: [
                CallbackQueryHandler(show_plan_confirmation, pattern=r'^select_plan_\d+$'),
                CallbackQueryHandler(show_payment_info, pattern=r'^confirm_purchase$'),
                CallbackQueryHandler(apply_discount_start, pattern=r'apply_discount_start')
            ],
            AWAIT_DISCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_and_validate_discount_code)],
            AWAIT_PAYMENT_SCREENSHOT: [MessageHandler(filters.PHOTO, receive_payment_screenshot)],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_flow, pattern='^buy_config_main$'),
            CallbackQueryHandler(start_command, pattern='^start_main$'),
            CommandHandler('start', start_command),
            CommandHandler('cancel', cancel_flow)
        ],
    )

    renewal_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_renewal_flow, pattern=r'^renew_service_\d+$')],
        states={
            RENEW_SELECT_PLAN: [
                CallbackQueryHandler(show_renewal_plan_confirmation, pattern=r'^renew_select_plan_\d+$'),
                CallbackQueryHandler(show_payment_info, pattern=r'^renew_confirm_purchase$'),
                CallbackQueryHandler(renew_apply_discount_start, pattern=r'renew_apply_discount_start')
            ],
            RENEW_AWAIT_DISCOUNT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_and_validate_discount_code)],
            RENEW_AWAIT_PAYMENT: [MessageHandler(filters.PHOTO, receive_renewal_payment)],
        },
        fallbacks=[
            CallbackQueryHandler(start_command, pattern='^start_main$'),
            CallbackQueryHandler(show_specific_service_details, pattern=r'^view_service_'),
            CommandHandler('start', start_command)
        ],
    )

    application.add_handler(admin_conv, group=1)
    application.add_handler(purchase_conv, group=1)
    application.add_handler(renewal_conv, group=1)

    application.add_handler(CommandHandler('start', start_command), group=2)

    application.add_handler(CallbackQueryHandler(admin_ask_panel_for_approval, pattern=r'^approve_auto_'), group=3)
    application.add_handler(CallbackQueryHandler(admin_approve_on_panel, pattern=r'^approve_on_panel_'), group=3)
    application.add_handler(CallbackQueryHandler(admin_review_order_reject, pattern=r'^reject_order_'), group=3)
    application.add_handler(CallbackQueryHandler(admin_manual_send_start, pattern=r'^approve_manual_'), group=3)
    application.add_handler(CallbackQueryHandler(admin_approve_renewal, pattern=r'^approve_renewal_'), group=3)
    application.add_handler(CallbackQueryHandler(get_free_config_handler, pattern=r'^get_free_config$'), group=3)
    application.add_handler(CallbackQueryHandler(my_services_handler, pattern=r'^my_services$'), group=3)
    application.add_handler(CallbackQueryHandler(show_specific_service_details, pattern=r'^view_service_\d+$'), group=3)
    application.add_handler(CallbackQueryHandler(start_command, pattern='^start_main$'), group=3)

    async def check_join_and_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await register_new_user(update.effective_user)
        await start_command(update, context)
    application.add_handler(CallbackQueryHandler(check_join_and_start, pattern='^check_join$'), group=3)

    application.add_handler(CallbackQueryHandler(dynamic_button_handler), group=4)

    logger.info("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
