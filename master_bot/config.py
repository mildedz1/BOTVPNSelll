# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

class MasterConfig:
    """Configuration for Master Bot"""
    
    # Bot Configuration
    MASTER_BOT_TOKEN = os.getenv("MASTER_BOT_TOKEN", "")
    MASTER_ADMIN_ID = int(os.getenv("MASTER_ADMIN_ID", "0"))
    
    # Database Configuration  
    MASTER_DB_NAME = os.getenv("MASTER_DB_NAME", "master_bot.db")
    
    # Server Configuration
    SERVER_HOST = os.getenv("SERVER_HOST", "localhost")
    SERVER_USER = os.getenv("SERVER_USER", "root")
    SERVER_PASSWORD = os.getenv("SERVER_PASSWORD", "")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "22"))
    
    # Docker Configuration
    DOCKER_REGISTRY = os.getenv("DOCKER_REGISTRY", "")
    VPN_BOT_IMAGE = os.getenv("VPN_BOT_IMAGE", "vpn-bot:latest")
    
    # Payment Configuration
    ZARINPAL_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "")
    IDPAY_API_KEY = os.getenv("IDPAY_API_KEY", "")
    
    # Pricing (تومان)
    MONTHLY_PRICE = int(os.getenv("MONTHLY_PRICE", "200000"))  # 200 هزار تومان
    YEARLY_PRICE = int(os.getenv("YEARLY_PRICE", "2000000"))   # 2 میلیون تومان (تخفیف)
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "master_bot.log")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration"""
        required_fields = ["MASTER_BOT_TOKEN", "MASTER_ADMIN_ID"]
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
        
        logging.basicConfig(
            format=log_format,
            level=getattr(logging, cls.LOG_LEVEL.upper()),
            handlers=[
                logging.FileHandler(cls.LOG_FILE, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

# Conversation States
class States:
    """Conversation states for master bot"""
    (
        # Main Menu
        MAIN_MENU,
        
        # Registration Process
        AWAIT_BOT_TOKEN,
        AWAIT_ADMIN_ID,
        AWAIT_CHANNEL_INFO,
        AWAIT_PAYMENT,
        
        # Subscription Management
        SUBSCRIPTION_MENU,
        RENEWAL_PAYMENT,
        
        # Admin Panel
        ADMIN_MENU,
        ADMIN_STATS,
        ADMIN_CUSTOMERS,
        ADMIN_SETTINGS,
        
        # Support
        SUPPORT_MENU,
        AWAIT_SUPPORT_MESSAGE,
    ) = range(15)

# Initialize configuration
config = MasterConfig()

# Validate configuration
if not config.validate():
    raise ValueError("Invalid master bot configuration. Please check your .env file.")

# Setup logging
config.setup_logging()