# -*- coding: utf-8 -*-
import requests
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from config import config
from database import query_db

logger = logging.getLogger(__name__)

@dataclass
class PanelConfig:
    """Configuration for a Marzban panel"""
    id: int
    name: str
    url: str
    username: str
    password: str
    is_active: bool = True

@dataclass
class UserConfig:
    """User configuration for VPN"""
    username: str
    data_limit: int
    expire_timestamp: int
    proxies: Dict[str, Any]
    inbounds: Dict[str, List[str]]
    status: str = "active"
    note: str = ""

class MarzbanAPIError(Exception):
    """Custom exception for Marzban API errors"""
    pass

class MarzbanAPI:
    """Secure Marzban API client with improved error handling"""
    
    def __init__(self, panel_config: PanelConfig):
        self.config = panel_config
        self.base_url = panel_config.url.rstrip('/')
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        
        # Set timeout and retry configuration
        self.session.timeout = 30
        self.session.headers.update({
            'User-Agent': 'VPN-Bot/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
    
    def _validate_panel_config(self) -> bool:
        """Validate panel configuration"""
        if not all([self.config.url, self.config.username, self.config.password]):
            logger.error(f"Invalid panel configuration for panel {self.config.id}")
            return False
        
        if not self.config.url.startswith(('http://', 'https://')):
            logger.error(f"Invalid URL format for panel {self.config.id}: {self.config.url}")
            return False
        
        return True
    
    def _handle_request_error(self, e: requests.RequestException, operation: str) -> str:
        """Handle and format request errors"""
        if isinstance(e, requests.exceptions.Timeout):
            return f"Timeout during {operation}"
        elif isinstance(e, requests.exceptions.ConnectionError):
            return f"Connection error during {operation}"
        elif isinstance(e, requests.exceptions.HTTPError):
            status_code = e.response.status_code if e.response else "Unknown"
            return f"HTTP {status_code} error during {operation}"
        else:
            return f"Request error during {operation}: {str(e)}"
    
    async def authenticate(self) -> bool:
        """Authenticate with the panel and get access token"""
        if not self._validate_panel_config():
            return False
        
        try:
            auth_data = {
                'username': self.config.username,
                'password': self.config.password
            }
            
            response = self.session.post(
                f"{self.base_url}/api/admin/token",
                data=auth_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=10
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get('access_token')
            if not self.access_token:
                logger.error(f"No access token received from panel {self.config.id}")
                return False
            
            # Update session headers with token
            self.session.headers.update({
                'Authorization': f'Bearer {self.access_token}'
            })
            
            logger.info(f"Successfully authenticated with panel {self.config.name}")
            return True
            
        except requests.RequestException as e:
            error_msg = self._handle_request_error(e, "authentication")
            logger.error(f"Authentication failed for panel {self.config.name}: {error_msg}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during authentication for panel {self.config.name}: {e}")
            return False
    
    async def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid access token"""
        if not self.access_token:
            return await self.authenticate()
        return True
    
    async def get_user(self, username: str) -> Tuple[Optional[Dict], str]:
        """Get user information from the panel"""
        if not await self._ensure_authenticated():
            return None, "Authentication failed"
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/user/{username}",
                timeout=15
            )
            
            if response.status_code == 404:
                return None, "User not found"
            
            response.raise_for_status()
            user_data = response.json()
            
            logger.info(f"Successfully retrieved user {username} from panel {self.config.name}")
            return user_data, "Success"
            
        except requests.RequestException as e:
            error_msg = self._handle_request_error(e, f"getting user {username}")
            logger.error(f"Failed to get user {username} from panel {self.config.name}: {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error getting user {username}: {e}"
            logger.error(error_msg)
            return None, error_msg
    
    async def get_all_users(self) -> Tuple[Optional[List[Dict]], str]:
        """Get all users from the panel"""
        if not await self._ensure_authenticated():
            return None, "Authentication failed"
        
        try:
            response = self.session.get(
                f"{self.base_url}/api/users",
                timeout=30
            )
            
            response.raise_for_status()
            data = response.json()
            users = data.get('users', [])
            
            logger.info(f"Successfully retrieved {len(users)} users from panel {self.config.name}")
            return users, "Success"
            
        except requests.RequestException as e:
            error_msg = self._handle_request_error(e, "getting all users")
            logger.error(f"Failed to get users from panel {self.config.name}: {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error getting users: {e}"
            logger.error(error_msg)
            return None, error_msg
    
    async def create_user(self, user_config: UserConfig) -> Tuple[Optional[Dict], str]:
        """Create a new user in the panel"""
        if not await self._ensure_authenticated():
            return None, "Authentication failed"
        
        try:
            user_data = {
                "status": user_config.status,
                "username": user_config.username,
                "note": user_config.note,
                "proxies": user_config.proxies,
                "data_limit": user_config.data_limit,
                "expire": user_config.expire_timestamp,
                "data_limit_reset_strategy": "no_reset",
                "inbounds": user_config.inbounds
            }
            
            response = self.session.post(
                f"{self.base_url}/api/user",
                json=user_data,
                timeout=20
            )
            
            response.raise_for_status()
            created_user = response.json()
            
            logger.info(f"Successfully created user {user_config.username} in panel {self.config.name}")
            return created_user, "Success"
            
        except requests.RequestException as e:
            error_msg = self._handle_request_error(e, f"creating user {user_config.username}")
            
            # Try to extract detailed error from response
            if e.response:
                try:
                    error_detail = e.response.json().get('detail', e.response.text)
                    if isinstance(error_detail, list):
                        error_detail = " ".join([d.get('msg', '') for d in error_detail if 'msg' in d])
                    error_msg = f"{error_msg}: {error_detail}"
                except:
                    pass
            
            logger.error(f"Failed to create user {user_config.username} in panel {self.config.name}: {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error creating user {user_config.username}: {e}"
            logger.error(error_msg)
            return None, error_msg
    
    async def update_user(self, username: str, updates: Dict[str, Any]) -> Tuple[Optional[Dict], str]:
        """Update user information"""
        if not await self._ensure_authenticated():
            return None, "Authentication failed"
        
        try:
            response = self.session.put(
                f"{self.base_url}/api/user/{username}",
                json=updates,
                timeout=20
            )
            
            response.raise_for_status()
            updated_user = response.json()
            
            logger.info(f"Successfully updated user {username} in panel {self.config.name}")
            return updated_user, "Success"
            
        except requests.RequestException as e:
            error_msg = self._handle_request_error(e, f"updating user {username}")
            logger.error(f"Failed to update user {username} in panel {self.config.name}: {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error updating user {username}: {e}"
            logger.error(error_msg)
            return None, error_msg

class VpnPanelAPI:
    """Enhanced VPN Panel API with improved security and error handling"""
    
    def __init__(self, panel_id: int):
        panel_data = query_db("SELECT * FROM panels WHERE id = ? AND is_active = 1", (panel_id,), one=True)
        if not panel_data:
            raise ValueError(f"Panel with ID {panel_id} not found or inactive")
        
        self.panel_config = PanelConfig(
            id=panel_data['id'],
            name=panel_data['name'],
            url=panel_data['url'],
            username=panel_data['username'],
            password=panel_data['password'],
            is_active=panel_data.get('is_active', True)
        )
        
        self.api = MarzbanAPI(self.panel_config)
        self.panel_id = panel_id
        self.base_url = self.panel_config.url.rstrip('/')
    
    def _generate_username(self, user_id: int) -> str:
        """Generate a unique username for the user"""
        return f"user_{user_id}_{uuid.uuid4().hex[:6]}"
    
    def _get_panel_inbounds(self) -> Dict[str, List[str]]:
        """Get manually configured inbounds for this panel"""
        inbounds = query_db(
            "SELECT protocol, tag FROM panel_inbounds WHERE panel_id = ? AND is_active = 1",
            (self.panel_id,)
        )
        
        if not inbounds:
            raise MarzbanAPIError(
                "No inbounds configured for this panel. Please configure inbounds through admin panel."
            )
        
        inbounds_by_protocol = {}
        for inbound in inbounds:
            protocol = inbound['protocol']
            tag = inbound['tag']
            
            if protocol not in inbounds_by_protocol:
                inbounds_by_protocol[protocol] = []
            inbounds_by_protocol[protocol].append(tag)
        
        return inbounds_by_protocol
    
    def _calculate_data_limit(self, traffic_gb: float) -> int:
        """Calculate data limit in bytes"""
        if traffic_gb <= 0:
            return 0  # Unlimited
        return int(traffic_gb * 1024 * 1024 * 1024)
    
    def _calculate_expire_timestamp(self, duration_days: int) -> int:
        """Calculate expiry timestamp"""
        if duration_days <= 0:
            return 0  # No expiry
        return int((datetime.now() + timedelta(days=duration_days)).timestamp())
    
    def _create_proxies_config(self, inbounds_by_protocol: Dict[str, List[str]]) -> Dict[str, Any]:
        """Create proxies configuration based on protocols"""
        proxies = {}
        for protocol in inbounds_by_protocol.keys():
            if protocol.lower() == "vless":
                proxies[protocol] = {"flow": "xtls-rprx-vision"}
            else:
                proxies[protocol] = {}
        return proxies
    
    async def create_user(self, user_id: int, plan: Dict) -> Tuple[Optional[str], Optional[str], str]:
        """Create a new user with the given plan"""
        try:
            # Get inbounds configuration
            inbounds_by_protocol = self._get_panel_inbounds()
            
            # Generate user configuration
            username = self._generate_username(user_id)
            data_limit = self._calculate_data_limit(float(plan['traffic_gb']))
            expire_timestamp = self._calculate_expire_timestamp(int(plan['duration_days']))
            proxies = self._create_proxies_config(inbounds_by_protocol)
            
            user_config = UserConfig(
                username=username,
                data_limit=data_limit,
                expire_timestamp=expire_timestamp,
                proxies=proxies,
                inbounds=inbounds_by_protocol
            )
            
            # Create user via API
            created_user, message = await self.api.create_user(user_config)
            
            if not created_user:
                return None, None, message
            
            # Generate subscription link
            subscription_path = created_user.get('subscription_url')
            if subscription_path:
                if subscription_path.startswith('http'):
                    config_link = subscription_path
                else:
                    config_link = f"{self.base_url}{subscription_path}"
            else:
                # Fallback to individual links
                config_link = "\n".join(created_user.get('links', []))
            
            logger.info(f"Successfully created user {username} for user_id {user_id}")
            return username, config_link, "Success"
            
        except MarzbanAPIError as e:
            logger.error(f"Panel configuration error: {e}")
            return None, None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error creating user for user_id {user_id}: {e}")
            return None, None, f"Internal error: {e}"
    
    async def get_user(self, marzban_username: str) -> Tuple[Optional[Dict], str]:
        """Get user information"""
        return await self.api.get_user(marzban_username)
    
    async def get_all_users(self) -> Tuple[Optional[List[Dict]], str]:
        """Get all users from the panel"""
        return await self.api.get_all_users()
    
    async def renew_user_in_panel(self, marzban_username: str, plan: Dict) -> Tuple[Optional[Dict], str]:
        """Renew user subscription with additional time and data"""
        try:
            # Get current user info
            current_user, message = await self.get_user(marzban_username)
            if not current_user:
                return None, f"User {marzban_username} not found for renewal: {message}"
            
            # Calculate new expiry time
            current_expire = current_user.get('expire', int(datetime.now().timestamp()))
            base_timestamp = max(current_expire, int(datetime.now().timestamp()))
            additional_seconds = int(plan['duration_days']) * 86400
            new_expire_timestamp = base_timestamp + additional_seconds
            
            # Calculate new data limit
            current_data_limit = current_user.get('data_limit', 0)
            additional_data_bytes = self._calculate_data_limit(float(plan['traffic_gb']))
            new_data_limit = current_data_limit + additional_data_bytes
            
            # Update user
            updates = {
                "expire": new_expire_timestamp,
                "data_limit": new_data_limit
            }
            
            updated_user, message = await self.api.update_user(marzban_username, updates)
            
            if updated_user:
                logger.info(f"Successfully renewed user {marzban_username}")
                return updated_user, "Success"
            else:
                return None, message
                
        except Exception as e:
            error_msg = f"Error renewing user {marzban_username}: {e}"
            logger.error(error_msg)
            return None, error_msg

# Utility functions
def bytes_to_gb(byte_val: int) -> float:
    """Convert bytes to gigabytes"""
    if not byte_val or byte_val == 0:
        return 0
    return round(byte_val / (1024**3), 2)

def format_expire_date(timestamp: int) -> str:
    """Format expire timestamp to readable date"""
    if not timestamp:
        return "نامحدود"
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')

def get_active_panels() -> List[Dict]:
    """Get all active panels"""
    return query_db("SELECT * FROM panels WHERE is_active = 1 ORDER BY id")