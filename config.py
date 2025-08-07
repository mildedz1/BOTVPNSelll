# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
import logging
from typing import Optional

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for the VPN bot"""
    
    # Bot Configuration
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    
    # Channel Configuration
    CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "@wings_iran")
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "-1001553094061"))
    
    # Database Configuration
    DB_NAME: str = os.getenv("DB_NAME", "bot.db")
    
    # Security Settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default_secret_key")
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")
    
    # Default Panel Configuration
    DEFAULT_PANEL_URL: str = os.getenv("DEFAULT_PANEL_URL", "https://your-panel.com")
    DEFAULT_PANEL_USER: str = os.getenv("DEFAULT_PANEL_USER", "admin")
    DEFAULT_PANEL_PASS: str = os.getenv("DEFAULT_PANEL_PASS", "password")
    
    # Payment Settings
    PAYMENT_TIMEOUT_HOURS: int = int(os.getenv("PAYMENT_TIMEOUT_HOURS", "24"))
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        required_fields = ["BOT_TOKEN", "ADMIN_ID"]
        missing_fields = []
        
        for field in required_fields:
            value = getattr(cls, field)
            if not value or (isinstance(value, str) and value.strip() == ""):
                missing_fields.append(field)
        
        if missing_fields:
            logging.error(f"Missing required configuration: {', '.join(missing_fields)}")
            return False
        
        return True
    
    @classmethod
    def setup_logging(cls) -> None:
        """Setup logging configuration"""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # Configure logging
        logging.basicConfig(
            format=log_format,
            level=getattr(logging, cls.LOG_LEVEL.upper()),
            handlers=[
                logging.FileHandler(cls.LOG_FILE, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        # Reduce telegram library logging
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("telegram").setLevel(logging.WARNING)

# Conversation States
class States:
    """Conversation states for the bot"""
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
        # Panel Inbound Management
        ADMIN_PANEL_INBOUNDS_MENU, ADMIN_PANEL_INBOUNDS_AWAIT_PROTOCOL, 
        ADMIN_PANEL_INBOUNDS_AWAIT_TAG,
    ) = range(48)

# Initialize configuration
config = Config()

# Validate configuration on import
if not config.validate():
    raise ValueError("Invalid configuration. Please check your .env file.")

# Setup logging
config.setup_logging()