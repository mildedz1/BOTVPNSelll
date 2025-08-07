# -*- coding: utf-8 -*-
import re
import logging
from typing import Optional, Union, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel, validator, ValidationError
from config import config

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error"""
    pass

class UserInputValidator:
    """Validator for user inputs"""
    
    @staticmethod
    def validate_card_number(card_number: str) -> bool:
        """Validate Iranian card number format"""
        if not card_number:
            return False
        
        # Remove spaces and dashes
        clean_number = re.sub(r'[\s\-]', '', card_number)
        
        # Check if it's 16 digits
        if not re.match(r'^\d{16}$', clean_number):
            return False
        
        return True
    
    @staticmethod
    def validate_holder_name(name: str) -> bool:
        """Validate card holder name"""
        if not name or len(name.strip()) < 2:
            return False
        
        # Allow Persian, Arabic and English characters
        pattern = r'^[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFFa-zA-Z\s]+$'
        return bool(re.match(pattern, name.strip()))
    
    @staticmethod
    def validate_price(price: str) -> Optional[int]:
        """Validate and convert price"""
        try:
            price_int = int(price.replace(',', ''))
            if price_int < 0:
                return None
            return price_int
        except (ValueError, AttributeError):
            return None
    
    @staticmethod
    def validate_duration_days(days: str) -> Optional[int]:
        """Validate duration in days"""
        try:
            days_int = int(days)
            if days_int < 0 or days_int > 365:  # Max 1 year
                return None
            return days_int
        except ValueError:
            return None
    
    @staticmethod
    def validate_traffic_gb(traffic: str) -> Optional[float]:
        """Validate traffic in GB"""
        traffic = traffic.strip().lower()
        
        if traffic in ['نامحدود', 'unlimited', '0']:
            return 0.0
        
        try:
            traffic_float = float(traffic)
            if traffic_float < 0 or traffic_float > 1000:  # Max 1TB
                return None
            return traffic_float
        except ValueError:
            return None
    
    @staticmethod
    def validate_discount_percentage(percentage: str) -> Optional[int]:
        """Validate discount percentage"""
        try:
            percent_int = int(percentage)
            if percent_int < 1 or percent_int > 100:
                return None
            return percent_int
        except ValueError:
            return None
    
    @staticmethod
    def validate_discount_code(code: str) -> bool:
        """Validate discount code format"""
        if not code or len(code) < 3 or len(code) > 20:
            return False
        
        # Allow alphanumeric characters only
        return bool(re.match(r'^[A-Z0-9]+$', code.upper()))
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format"""
        if not url:
            return False
        
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        return bool(url_pattern.match(url))
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate panel username"""
        if not username or len(username) < 3 or len(username) > 50:
            return False
        
        # Allow alphanumeric and some special characters
        return bool(re.match(r'^[a-zA-Z0-9_.-]+$', username))
    
    @staticmethod
    def validate_protocol(protocol: str) -> bool:
        """Validate VPN protocol"""
        valid_protocols = ['vless', 'vmess', 'trojan', 'shadowsocks', 'wireguard']
        return protocol.lower() in valid_protocols
    
    @staticmethod
    def validate_tag(tag: str) -> bool:
        """Validate inbound tag"""
        if not tag or len(tag) < 1 or len(tag) > 50:
            return False
        
        # Allow alphanumeric, underscore, dash
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', tag))
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """Sanitize text input"""
        if not text:
            return ""
        
        # Remove potential harmful characters
        sanitized = re.sub(r'[<>"\']', '', text.strip())
        
        # Limit length
        return sanitized[:max_length]

class PlanModel(BaseModel):
    """Pydantic model for plan validation"""
    name: str
    description: Optional[str] = ""
    price: int
    duration_days: int
    traffic_gb: float
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Plan name must be at least 2 characters')
        return v.strip()
    
    @validator('price')
    def validate_price(cls, v):
        if v < 0:
            raise ValueError('Price cannot be negative')
        return v
    
    @validator('duration_days')
    def validate_duration(cls, v):
        if v < 0 or v > 365:
            raise ValueError('Duration must be between 0 and 365 days')
        return v
    
    @validator('traffic_gb')
    def validate_traffic(cls, v):
        if v < 0 or v > 1000:
            raise ValueError('Traffic must be between 0 and 1000 GB')
        return v

class DiscountCodeModel(BaseModel):
    """Pydantic model for discount code validation"""
    code: str
    percentage: int
    usage_limit: int
    expiry_days: Optional[int] = None
    
    @validator('code')
    def validate_code(cls, v):
        if not UserInputValidator.validate_discount_code(v):
            raise ValueError('Invalid discount code format')
        return v.upper()
    
    @validator('percentage')
    def validate_percentage(cls, v):
        if v < 1 or v > 100:
            raise ValueError('Percentage must be between 1 and 100')
        return v
    
    @validator('usage_limit')
    def validate_usage_limit(cls, v):
        if v < 0:
            raise ValueError('Usage limit cannot be negative')
        return v
    
    @validator('expiry_days')
    def validate_expiry_days(cls, v):
        if v is not None and (v < 1 or v > 365):
            raise ValueError('Expiry days must be between 1 and 365')
        return v

class PanelModel(BaseModel):
    """Pydantic model for panel validation"""
    name: str
    url: str
    username: str
    password: str
    
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Panel name must be at least 2 characters')
        return v.strip()
    
    @validator('url')
    def validate_url(cls, v):
        if not UserInputValidator.validate_url(v):
            raise ValueError('Invalid URL format')
        return v.rstrip('/')
    
    @validator('username')
    def validate_username(cls, v):
        if not UserInputValidator.validate_username(v):
            raise ValueError('Invalid username format')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        if not v or len(v) < 3:
            raise ValueError('Password must be at least 3 characters')
        return v

class SecurityValidator:
    """Security-related validators"""
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == config.ADMIN_ID
    
    @staticmethod
    def validate_user_id(user_id: Union[str, int]) -> Optional[int]:
        """Validate and convert user ID"""
        try:
            uid = int(user_id)
            if uid <= 0:
                return None
            return uid
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal"""
        if not filename:
            return "file"
        
        # Remove path separators and dangerous characters
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
        safe_name = re.sub(r'\.\.', '_', safe_name)
        
        # Limit length
        return safe_name[:100]
    
    @staticmethod
    def validate_message_name(name: str) -> bool:
        """Validate message name for database"""
        if not name or len(name) < 2 or len(name) > 50:
            return False
        
        # Allow alphanumeric and underscore only
        return bool(re.match(r'^[a-zA-Z0-9_]+$', name))

class RateLimiter:
    """Simple rate limiter"""
    
    def __init__(self):
        self.requests = {}
    
    def is_allowed(self, user_id: int, max_requests: int = None) -> bool:
        """Check if user is within rate limit"""
        if not max_requests:
            max_requests = config.RATE_LIMIT_PER_MINUTE
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old requests
        if user_id in self.requests:
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if req_time > minute_ago
            ]
        else:
            self.requests[user_id] = []
        
        # Check limit
        if len(self.requests[user_id]) >= max_requests:
            return False
        
        # Add current request
        self.requests[user_id].append(now)
        return True
    
    def get_remaining_requests(self, user_id: int) -> int:
        """Get remaining requests for user"""
        max_requests = config.RATE_LIMIT_PER_MINUTE
        current_requests = len(self.requests.get(user_id, []))
        return max(0, max_requests - current_requests)

# Global instances
rate_limiter = RateLimiter()
validator = UserInputValidator()
security = SecurityValidator()

# Helper functions
def validate_plan_data(data: Dict[str, Any]) -> PlanModel:
    """Validate plan data using Pydantic"""
    try:
        return PlanModel(**data)
    except ValidationError as e:
        logger.error(f"Plan validation error: {e}")
        raise ValidationError(f"Invalid plan data: {e}")

def validate_discount_data(data: Dict[str, Any]) -> DiscountCodeModel:
    """Validate discount code data"""
    try:
        return DiscountCodeModel(**data)
    except ValidationError as e:
        logger.error(f"Discount code validation error: {e}")
        raise ValidationError(f"Invalid discount code data: {e}")

def validate_panel_data(data: Dict[str, Any]) -> PanelModel:
    """Validate panel data"""
    try:
        return PanelModel(**data)
    except ValidationError as e:
        logger.error(f"Panel validation error: {e}")
        raise ValidationError(f"Invalid panel data: {e}")

def check_rate_limit(user_id: int) -> bool:
    """Check if user is within rate limit"""
    return rate_limiter.is_allowed(user_id)