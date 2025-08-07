# -*- coding: utf-8 -*-
import sqlite3
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from contextlib import contextmanager
from config import config

logger = logging.getLogger(__name__)

class MasterDatabase:
    """Database manager for Master Bot"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or config.MASTER_DB_NAME
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
            
            # Customers table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    phone TEXT,
                    email TEXT,
                    registration_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'suspended', 'cancelled')),
                    total_paid INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Subscriptions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    bot_token TEXT NOT NULL,
                    admin_id INTEGER NOT NULL,
                    channel_username TEXT,
                    channel_id INTEGER,
                    plan_type TEXT DEFAULT 'monthly' CHECK(plan_type IN ('monthly', 'yearly')),
                    price INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'suspended')),
                    container_id TEXT,
                    bot_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
                )
            """)
            
            # Payments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    subscription_id INTEGER,
                    amount INTEGER NOT NULL,
                    payment_method TEXT DEFAULT 'aqay' CHECK(payment_method IN ('aqay', 'card_to_card', 'crypto')),
                    transaction_id TEXT,
                    authority TEXT,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'failed', 'refunded')),
                    payment_date TEXT,
                    card_id INTEGER,
                    wallet_id INTEGER,
                    crypto_amount REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id),
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
                    FOREIGN KEY (card_id) REFERENCES payment_cards(id),
                    FOREIGN KEY (wallet_id) REFERENCES crypto_wallets(id)
                )
            """)
            
            # Payment Cards table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_number TEXT NOT NULL,
                    card_name TEXT NOT NULL,
                    bank_name TEXT,
                    instructions TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    priority INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Crypto Wallets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crypto_wallets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_address TEXT NOT NULL,
                    crypto_type TEXT NOT NULL,
                    network TEXT,
                    instructions TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    priority INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Bot instances table (for monitoring)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_instances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER NOT NULL,
                    container_id TEXT UNIQUE NOT NULL,
                    container_name TEXT NOT NULL,
                    port INTEGER,
                    status TEXT DEFAULT 'running' CHECK(status IN ('running', 'stopped', 'error')),
                    last_check TEXT,
                    cpu_usage REAL,
                    memory_usage REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
                )
            """)
            
            # Support tickets table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'resolved', 'closed')),
                    priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
                    admin_response TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (customer_id) REFERENCES customers(id)
                )
            """)
            
            # Settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_customers_user_id ON customers(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_subscriptions_customer_id ON subscriptions(customer_id)",
                "CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)",
                "CREATE INDEX IF NOT EXISTS idx_payments_customer_id ON payments(customer_id)",
                "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
                "CREATE INDEX IF NOT EXISTS idx_bot_instances_subscription_id ON bot_instances(subscription_id)",
                "CREATE INDEX IF NOT EXISTS idx_support_tickets_customer_id ON support_tickets(customer_id)"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)
            
            conn.commit()
            self._initialize_default_data(cursor, conn)
    
    def _initialize_default_data(self, cursor, conn):
        """Initialize default settings"""
        default_settings = {
            'monthly_price': str(config.MONTHLY_PRICE),
            'yearly_price': str(config.YEARLY_PRICE),
            'welcome_message': '🎉 به سرویس Master Bot خوش آمدید!\n\nبا این ربات می‌توانید ربات فروش VPN شخصی خود را راه‌اندازی کنید.',
            'payment_message': '💳 برای پرداخت روی دکمه زیر کلیک کنید:',
            'success_message': '✅ پرداخت شما با موفقیت انجام شد!\nربات شما در حال راه‌اندازی است...',
            'support_contact': '@YourSupportBot'
        }
        
        for key, value in default_settings.items():
            cursor.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
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

class CustomerRepository:
    """Repository for customer operations"""
    
    def __init__(self, db: MasterDatabase):
        self.db = db
    
    def create_customer(self, user_id: int, first_name: str, username: str = None) -> Optional[int]:
        """Create a new customer"""
        query = """
            INSERT INTO customers (user_id, first_name, username) 
            VALUES (?, ?, ?)
        """
        return self.db.execute_query(query, (user_id, first_name, username))
    
    def get_customer(self, user_id: int) -> Optional[Dict]:
        """Get customer by user_id"""
        query = "SELECT * FROM customers WHERE user_id = ?"
        return self.db.fetch_one(query, (user_id,))
    
    def get_customer_by_id(self, customer_id: int) -> Optional[Dict]:
        """Get customer by id"""
        query = "SELECT * FROM customers WHERE id = ?"
        return self.db.fetch_one(query, (customer_id,))
    
    def update_customer(self, user_id: int, **kwargs) -> bool:
        """Update customer information"""
        if not kwargs:
            return False
        
        set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
        query = f"UPDATE customers SET {set_clause} WHERE user_id = ?"
        params = list(kwargs.values()) + [user_id]
        
        return self.db.execute_query(query, tuple(params)) is not None
    
    def get_all_customers(self) -> List[Dict]:
        """Get all customers"""
        query = "SELECT * FROM customers ORDER BY created_at DESC"
        return self.db.fetch_all(query)

class SubscriptionRepository:
    """Repository for subscription operations"""
    
    def __init__(self, db: MasterDatabase):
        self.db = db
    
    def create_subscription(self, customer_id: int, bot_token: str, admin_id: int, 
                          plan_type: str, price: int, **kwargs) -> Optional[int]:
        """Create a new subscription"""
        start_date = datetime.now().isoformat()
        
        if plan_type == 'monthly':
            end_date = (datetime.now() + timedelta(days=30)).isoformat()
        else:  # yearly
            end_date = (datetime.now() + timedelta(days=365)).isoformat()
        
        query = """
            INSERT INTO subscriptions 
            (customer_id, bot_token, admin_id, plan_type, price, start_date, end_date, channel_username, channel_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        return self.db.execute_query(query, (
            customer_id, bot_token, admin_id, plan_type, price, start_date, end_date,
            kwargs.get('channel_username'), kwargs.get('channel_id')
        ))
    
    def get_subscription(self, subscription_id: int) -> Optional[Dict]:
        """Get subscription by id"""
        query = "SELECT * FROM subscriptions WHERE id = ?"
        return self.db.fetch_one(query, (subscription_id,))
    
    def get_customer_subscriptions(self, customer_id: int) -> List[Dict]:
        """Get all subscriptions for a customer"""
        query = "SELECT * FROM subscriptions WHERE customer_id = ? ORDER BY created_at DESC"
        return self.db.fetch_all(query, (customer_id,))
    
    def get_active_subscriptions(self) -> List[Dict]:
        """Get all active subscriptions"""
        query = "SELECT * FROM subscriptions WHERE status = 'active' ORDER BY end_date"
        return self.db.fetch_all(query)
    
    def get_expiring_subscriptions(self, days: int = 3) -> List[Dict]:
        """Get subscriptions expiring in X days"""
        expire_date = (datetime.now() + timedelta(days=days)).isoformat()
        query = """
            SELECT s.*, c.user_id, c.first_name 
            FROM subscriptions s 
            JOIN customers c ON s.customer_id = c.id 
            WHERE s.status = 'active' AND s.end_date <= ?
        """
        return self.db.fetch_all(query, (expire_date,))
    
    def update_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Update subscription"""
        if not kwargs:
            return False
        
        kwargs['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
        query = f"UPDATE subscriptions SET {set_clause} WHERE id = ?"
        params = list(kwargs.values()) + [subscription_id]
        
        return self.db.execute_query(query, tuple(params)) is not None
    
    def extend_subscription(self, subscription_id: int, days: int) -> bool:
        """Extend subscription by X days"""
        subscription = self.get_subscription(subscription_id)
        if not subscription:
            return False
        
        current_end = datetime.fromisoformat(subscription['end_date'])
        new_end = current_end + timedelta(days=days)
        
        return self.update_subscription(subscription_id, end_date=new_end.isoformat())

# Initialize database
master_db = MasterDatabase()
customer_repo = CustomerRepository(master_db)
subscription_repo = SubscriptionRepository(master_db)

# Legacy functions for compatibility
def query_db(query: str, args: tuple = (), one: bool = False):
    """Legacy function for backward compatibility"""
    if one:
        return master_db.fetch_one(query, args)
    else:
        return master_db.fetch_all(query, args)

def execute_db(query: str, args: tuple = ()) -> Optional[int]:
    """Legacy function for backward compatibility"""
    return master_db.execute_query(query, args)