#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master Bot Startup Script
Initializes database, sets up environment, and starts the bot
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('master_bot.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("Logging setup completed")
    return logger

def check_environment():
    """Check if all required environment variables are set"""
    logger = logging.getLogger(__name__)
    
    try:
        from config import config
        
        # Check critical settings
        required_vars = [
            'MASTER_BOT_TOKEN',
            'MASTER_ADMIN_ID',
            'MASTER_DB_NAME'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(config, var, None):
                missing_vars.append(var)
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            return False
        
        logger.info("Environment check passed")
        return True
        
    except Exception as e:
        logger.error(f"Error checking environment: {e}")
        return False

def initialize_database():
    """Initialize database and create tables"""
    logger = logging.getLogger(__name__)
    
    try:
        from database import master_db
        logger.info("Database initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False

def setup_payment_methods():
    """Setup default payment methods if not exists"""
    logger = logging.getLogger(__name__)
    
    try:
        from database import query_db, execute_db
        
        # Check if payment cards exist
        cards = query_db("SELECT COUNT(*) as count FROM payment_cards", one=True)
        if cards['count'] == 0:
            logger.info("Setting up default payment methods...")
            
            # Add sample card
            execute_db("""
                INSERT INTO payment_cards (card_number, card_name, bank_name, is_active)
                VALUES (?, ?, ?, ?)
            """, ("6037-0000-0000-0000", "نام دارنده کارت", "بانک ملی", 1))
            
            # Add sample crypto wallet
            execute_db("""
                INSERT INTO crypto_wallets (currency, wallet_address, network, is_active)
                VALUES (?, ?, ?, ?)
            """, ("USDT", "TQn9Y2khEsLMWD2iNzEjwhXSlYwBEDWi7g", "TRC20", 1))
            
            logger.info("Default payment methods added")
        
        return True
        
    except Exception as e:
        logger.error(f"Error setting up payment methods: {e}")
        return False

def setup_default_settings():
    """Setup default system settings"""
    logger = logging.getLogger(__name__)
    
    try:
        from database import execute_db, query_db
        
        # Default settings
        default_settings = [
            ('aqay_enabled', 'true'),
            ('card_to_card_enabled', 'true'),
            ('crypto_enabled', 'true'),
            ('default_dollar_price', '70000'),
            ('trial_enabled', 'true'),
            ('trial_days', '3'),
            ('trial_traffic_limit_gb', '10'),
            ('referrer_percentage', '15'),
            ('referee_discount_percentage', '10'),
            ('min_payout_amount', '50000')
        ]
        
        for key, value in default_settings:
            existing = query_db("SELECT id FROM settings WHERE key = ?", (key,), one=True)
            if not existing:
                execute_db("""
                    INSERT INTO settings (key, value, description)
                    VALUES (?, ?, ?)
                """, (key, value, f"Default setting for {key}"))
        
        logger.info("Default settings configured")
        return True
        
    except Exception as e:
        logger.error(f"Error setting up default settings: {e}")
        return False

async def start_bot():
    """Start the Master Bot"""
    logger = logging.getLogger(__name__)
    
    try:
        from master_bot import main
        logger.info("Starting Master Bot...")
        await main()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise

def main():
    """Main startup function"""
    print("🚀 Master Bot Startup")
    print("=" * 50)
    
    # Setup logging
    logger = setup_logging()
    logger.info("Master Bot startup initiated")
    
    # Check environment
    print("📋 Checking environment...")
    if not check_environment():
        print("❌ Environment check failed!")
        sys.exit(1)
    print("✅ Environment check passed")
    
    # Initialize database
    print("🗄️  Initializing database...")
    if not initialize_database():
        print("❌ Database initialization failed!")
        sys.exit(1)
    print("✅ Database initialized")
    
    # Setup payment methods
    print("💳 Setting up payment methods...")
    if not setup_payment_methods():
        print("❌ Payment methods setup failed!")
        sys.exit(1)
    print("✅ Payment methods configured")
    
    # Setup default settings
    print("⚙️  Configuring default settings...")
    if not setup_default_settings():
        print("❌ Default settings configuration failed!")
        sys.exit(1)
    print("✅ Default settings configured")
    
    print("=" * 50)
    print("🎉 Master Bot is ready to start!")
    print("=" * 50)
    
    # Start bot
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("\n👋 Master Bot stopped gracefully")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()