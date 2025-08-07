# -*- coding: utf-8 -*-
import sqlite3
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from contextlib import contextmanager
from config import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Secure database manager with connection pooling and error handling"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or config.DB_NAME
        self._setup_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_name, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def _setup_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create tables with proper constraints
            tables = [
                """CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    join_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS messages (
                    message_name TEXT PRIMARY KEY,
                    text TEXT,
                    file_id TEXT,
                    file_type TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS buttons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    menu_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    target TEXT NOT NULL,
                    is_url BOOLEAN DEFAULT 0,
                    row INTEGER NOT NULL DEFAULT 1,
                    col INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    price INTEGER NOT NULL CHECK(price >= 0),
                    duration_days INTEGER NOT NULL CHECK(duration_days >= 0),
                    traffic_gb REAL NOT NULL CHECK(traffic_gb >= 0),
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_number TEXT NOT NULL,
                    holder_name TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS free_trials (
                    user_id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )""",
                
                """CREATE TABLE IF NOT EXISTS discount_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    percentage INTEGER NOT NULL CHECK(percentage > 0 AND percentage <= 100),
                    usage_limit INTEGER NOT NULL CHECK(usage_limit >= 0),
                    times_used INTEGER DEFAULT 0 CHECK(times_used >= 0),
                    expiry_date TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS panels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    url TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                
                """CREATE TABLE IF NOT EXISTS panel_inbounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    panel_id INTEGER NOT NULL,
                    protocol TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(panel_id, tag),
                    FOREIGN KEY (panel_id) REFERENCES panels(id) ON DELETE CASCADE
                )""",
                
                """CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_id INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                    marzban_username TEXT,
                    screenshot_file_id TEXT,
                    panel_id INTEGER,
                    discount_code TEXT,
                    final_price INTEGER,
                    last_reminder_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (plan_id) REFERENCES plans(id),
                    FOREIGN KEY (panel_id) REFERENCES panels(id)
                )"""
            ]
            
            for table_sql in tables:
                cursor.execute(table_sql)
            
            # Create indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)",
                "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_buttons_menu_name ON buttons(menu_name)",
                "CREATE INDEX IF NOT EXISTS idx_discount_codes_code ON discount_codes(code)",
                "CREATE INDEX IF NOT EXISTS idx_panel_inbounds_panel_id ON panel_inbounds(panel_id)"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            conn.commit()
            
            # Initialize default data
            self._initialize_default_data(cursor, conn)
    
    def _initialize_default_data(self, cursor, conn):
        """Initialize default messages, settings, etc."""
        default_messages = {
            'start_main': ('🖐 سلام! به ربات فروش کانفیگ ما خوش آمدید.\nبرای شروع از دکمه‌های زیر استفاده کنید.', None, None),
            'admin_panel_main': ('🖥️ پنل مدیریت ربات. لطفا یک گزینه را انتخاب کنید.', None, None),
            'buy_config_main': ('📡 **خرید کانفیگ**\n\nلطفا یکی از پلن‌های زیر را انتخاب کنید:', None, None),
            'payment_info_text': ('💳 **اطلاعات پرداخت** 💳\n\nمبلغ پلن انتخابی را به یکی از کارت‌های زیر واریز کرده و سپس اسکرین‌شات رسید را در همین صفحه ارسال نمایید.', None, None),
            'renewal_reminder_text': ('⚠️ **یادآوری تمدید سرویس**\n\nکاربر گرامی، اعتبار سرویس شما با نام کاربری `{marzban_username}` رو به اتمام است.\n\n{details}\n\nبرای جلوگیری از قطع شدن سرویس، لطفاً از طریق دکمه "سرویس من" در منوی اصلی ربات اقدام به تمدید نمایید.', None, None)
        }
        
        for name, (text, f_id, f_type) in default_messages.items():
            cursor.execute(
                "INSERT OR IGNORE INTO messages (message_name, text, file_id, file_type) VALUES (?, ?, ?, ?)",
                (name, text, f_id, f_type)
            )
        
        # Check if buttons exist for start_main
        cursor.execute("SELECT COUNT(*) as count FROM buttons WHERE menu_name = ?", ('start_main',))
        if cursor.fetchone()['count'] == 0:
            default_buttons = [
                ('🚀 خرید کانفیگ', 'buy_config_main', 0, 1, 1),
                ('📦 سرویس من', 'my_services', 0, 1, 2),
                ('🎫 کانفیگ تست رایگان', 'get_free_config', 0, 2, 1),
            ]
            for btn_text, btn_target, btn_is_url, btn_row, btn_col in default_buttons:
                cursor.execute(
                    "INSERT INTO buttons (menu_name, text, target, is_url, row, col) VALUES (?, ?, ?, ?, ?, ?)",
                    ('start_main', btn_text, btn_target, btn_is_url, btn_row, btn_col)
                )
        
        # Initialize default settings
        default_settings = {
            'free_trial_days': '1',
            'free_trial_gb': '0.2',
            'free_trial_status': '1'
        }
        for key, value in default_settings.items():
            cursor.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
        
        # Initialize default card if none exists
        cursor.execute("SELECT COUNT(*) as count FROM cards")
        if cursor.fetchone()['count'] == 0:
            cursor.execute(
                "INSERT INTO cards (card_number, holder_name) VALUES (?, ?)",
                ("6037-0000-0000-0000", "نام دارنده کارت")
            )
        
        # Migrate old panel settings to panels table if needed
        cursor.execute("SELECT COUNT(*) as count FROM panels")
        if cursor.fetchone()['count'] == 0:
            cursor.execute(
                "INSERT INTO panels (name, url, username, password) VALUES (?, ?, ?, ?)",
                ('پنل اصلی (پیش‌فرض)', config.DEFAULT_PANEL_URL, config.DEFAULT_PANEL_USER, config.DEFAULT_PANEL_PASS)
            )
        
        conn.commit()
    
    def execute_query(self, query: str, params: tuple = ()) -> Optional[int]:
        """Execute a query and return last row id"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Execute query error: {e}")
            return None
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict]:
        """Fetch one row as dictionary"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Fetch one error: {e}")
            return None
    
    def fetch_all(self, query: str, params: tuple = ()) -> List[Dict]:
        """Fetch all rows as list of dictionaries"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Fetch all error: {e}")
            return []
    
    def execute_many(self, query: str, params_list: List[tuple]) -> bool:
        """Execute query with multiple parameter sets"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Execute many error: {e}")
            return False

# Database operations for specific entities
class UserRepository:
    """Repository for user operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def create_user(self, user_id: int, first_name: str) -> bool:
        """Create a new user"""
        query = "INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)"
        result = self.db.execute_query(query, (user_id, first_name))
        return result is not None
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        query = "SELECT * FROM users WHERE user_id = ?"
        return self.db.fetch_one(query, (user_id,))
    
    def user_exists(self, user_id: int) -> bool:
        """Check if user exists"""
        query = "SELECT 1 FROM users WHERE user_id = ?"
        return self.db.fetch_one(query, (user_id,)) is not None
    
    def get_all_users(self, exclude_admin: bool = True) -> List[Dict]:
        """Get all users"""
        if exclude_admin:
            query = "SELECT * FROM users WHERE user_id != ? AND is_active = 1"
            return self.db.fetch_all(query, (config.ADMIN_ID,))
        else:
            query = "SELECT * FROM users WHERE is_active = 1"
            return self.db.fetch_all()
    
    def deactivate_users(self, user_ids: List[int]) -> bool:
        """Deactivate multiple users"""
        if not user_ids:
            return True
        
        placeholders = ','.join('?' for _ in user_ids)
        query = f"UPDATE users SET is_active = 0 WHERE user_id IN ({placeholders})"
        return self.db.execute_query(query, tuple(user_ids)) is not None

class PlanRepository:
    """Repository for plan operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    def create_plan(self, name: str, description: str, price: int, 
                   duration_days: int, traffic_gb: float) -> Optional[int]:
        """Create a new plan"""
        query = """INSERT INTO plans (name, description, price, duration_days, traffic_gb) 
                   VALUES (?, ?, ?, ?, ?)"""
        return self.db.execute_query(query, (name, description, price, duration_days, traffic_gb))
    
    def get_plan(self, plan_id: int) -> Optional[Dict]:
        """Get plan by ID"""
        query = "SELECT * FROM plans WHERE id = ? AND is_active = 1"
        return self.db.fetch_one(query, (plan_id,))
    
    def get_all_plans(self, active_only: bool = True) -> List[Dict]:
        """Get all plans"""
        if active_only:
            query = "SELECT * FROM plans WHERE is_active = 1 ORDER BY price"
        else:
            query = "SELECT * FROM plans ORDER BY price"
        return self.db.fetch_all(query)
    
    def update_plan(self, plan_id: int, **kwargs) -> bool:
        """Update plan fields"""
        if not kwargs:
            return False
        
        # Add updated_at timestamp
        kwargs['updated_at'] = datetime.now().isoformat()
        
        set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
        query = f"UPDATE plans SET {set_clause} WHERE id = ?"
        params = list(kwargs.values()) + [plan_id]
        
        return self.db.execute_query(query, tuple(params)) is not None
    
    def delete_plan(self, plan_id: int) -> bool:
        """Soft delete plan"""
        query = "UPDATE plans SET is_active = 0 WHERE id = ?"
        return self.db.execute_query(query, (plan_id,)) is not None

# Initialize database manager
db_manager = DatabaseManager()

# Initialize repositories
user_repo = UserRepository(db_manager)
plan_repo = PlanRepository(db_manager)

# Legacy functions for backward compatibility
def query_db(query: str, args: tuple = (), one: bool = False) -> Union[Dict, List[Dict], None]:
    """Legacy function for backward compatibility"""
    if one:
        return db_manager.fetch_one(query, args)
    else:
        return db_manager.fetch_all(query, args)

def execute_db(query: str, args: tuple = ()) -> Optional[int]:
    """Legacy function for backward compatibility"""
    return db_manager.execute_query(query, args)