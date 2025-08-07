# -*- coding: utf-8 -*-
"""
Free Trial System for Master Bot
Handles trial account creation, management, and conversion
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from database import execute_db, query_db, customer_repo
from deployment import deployment_service

logger = logging.getLogger(__name__)

class TrialManager:
    """Manages trial accounts"""
    
    # Default trial settings
    DEFAULT_TRIAL_DAYS = 3
    DEFAULT_TRAFFIC_LIMIT_GB = 10
    
    @staticmethod
    def get_trial_settings() -> Dict:
        """Get current trial settings"""
        
        settings = query_db("""
            SELECT key, value FROM settings 
            WHERE key IN ('trial_enabled', 'trial_days', 'trial_traffic_limit_gb', 'trial_per_phone')
        """)
        
        result = {
            'trial_enabled': True,
            'trial_days': TrialManager.DEFAULT_TRIAL_DAYS,
            'trial_traffic_limit_gb': TrialManager.DEFAULT_TRAFFIC_LIMIT_GB,
            'trial_per_phone': True  # One trial per phone number
        }
        
        for setting in settings:
            if setting['key'] == 'trial_enabled':
                result['trial_enabled'] = setting['value'].lower() == 'true'
            elif setting['key'] == 'trial_days':
                result['trial_days'] = int(setting['value'])
            elif setting['key'] == 'trial_traffic_limit_gb':
                result['trial_traffic_limit_gb'] = int(setting['value'])
            elif setting['key'] == 'trial_per_phone':
                result['trial_per_phone'] = setting['value'].lower() == 'true'
        
        return result
    
    @staticmethod
    def check_trial_eligibility(customer_id: int, phone_number: str = None) -> Tuple[bool, str]:
        """Check if customer is eligible for trial"""
        
        settings = TrialManager.get_trial_settings()
        
        if not settings['trial_enabled']:
            return False, "سرویس تست رایگان غیرفعال است"
        
        # Check if customer already has a trial
        existing_trial = query_db("""
            SELECT id FROM trial_accounts 
            WHERE customer_id = ?
        """, (customer_id,), one=True)
        
        if existing_trial:
            return False, "شما قبلاً از تست رایگان استفاده کرده‌اید"
        
        # Check if customer has any paid subscription
        paid_subscription = query_db("""
            SELECT id FROM subscriptions 
            WHERE customer_id = ?
        """, (customer_id,), one=True)
        
        if paid_subscription:
            return False, "مشتریان با اشتراک پولی نمی‌توانند از تست رایگان استفاده کنند"
        
        # Check phone number limit if enabled
        if settings['trial_per_phone'] and phone_number:
            phone_trial = query_db("""
                SELECT ta.id FROM trial_accounts ta
                JOIN customers c ON ta.customer_id = c.id
                WHERE c.phone_number = ?
            """, (phone_number,), one=True)
            
            if phone_trial:
                return False, "این شماره تلفن قبلاً از تست رایگان استفاده کرده است"
        
        return True, "مجاز به دریافت تست رایگان"
    
    @staticmethod
    async def create_trial_account(
        customer_id: int, 
        bot_username: str, 
        admin_id: int,
        channel_username: str = None
    ) -> Tuple[bool, str, Optional[Dict]]:
        """Create trial account for customer"""
        
        try:
            settings = TrialManager.get_trial_settings()
            
            # Check eligibility
            customer = customer_repo.get_customer_by_id(customer_id)
            if not customer:
                return False, "مشتری یافت نشده", None
            
            is_eligible, message = TrialManager.check_trial_eligibility(
                customer_id, customer.get('phone_number')
            )
            
            if not is_eligible:
                return False, message, None
            
            # Calculate expiry date
            expires_at = (datetime.now() + timedelta(days=settings['trial_days'])).isoformat()
            
            # Create trial record
            trial_id = execute_db("""
                INSERT INTO trial_accounts 
                (customer_id, trial_days, traffic_limit_gb, expires_at)
                VALUES (?, ?, ?, ?)
            """, (
                customer_id,
                settings['trial_days'],
                settings['trial_traffic_limit_gb'],
                expires_at
            ))
            
            # Deploy trial bot (similar to regular bot but with limitations)
            deployment_data = {
                'customer_id': customer_id,
                'bot_username': bot_username,
                'admin_id': admin_id,
                'channel_username': channel_username,
                'plan_type': 'trial',
                'trial_id': trial_id,
                'traffic_limit': settings['trial_traffic_limit_gb'],
                'expires_at': expires_at
            }
            
            deployment_result = await deployment_service.deploy_trial_bot(deployment_data)
            
            if deployment_result.get('success'):
                # Update trial record with deployment info
                execute_db("""
                    UPDATE trial_accounts 
                    SET bot_instance_id = ?, vpn_username = ?
                    WHERE id = ?
                """, (
                    deployment_result['bot_instance_id'],
                    deployment_result['vpn_username'],
                    trial_id
                ))
                
                trial_info = {
                    'trial_id': trial_id,
                    'bot_username': bot_username,
                    'vpn_username': deployment_result['vpn_username'],
                    'trial_days': settings['trial_days'],
                    'traffic_limit_gb': settings['trial_traffic_limit_gb'],
                    'expires_at': expires_at,
                    'bot_instance_id': deployment_result['bot_instance_id']
                }
                
                logger.info(f"Created trial account {trial_id} for customer {customer_id}")
                return True, "تست رایگان با موفقیت فعال شد", trial_info
            else:
                # Delete trial record if deployment failed
                execute_db("DELETE FROM trial_accounts WHERE id = ?", (trial_id,))
                return False, f"خطا در راه‌اندازی: {deployment_result.get('error', 'نامشخص')}", None
                
        except Exception as e:
            logger.error(f"Error creating trial account: {e}")
            return False, "خطا در ایجاد تست رایگان", None
    
    @staticmethod
    def get_trial_info(customer_id: int) -> Optional[Dict]:
        """Get trial account info for customer"""
        
        return query_db("""
            SELECT ta.*, bi.bot_username, bi.container_name
            FROM trial_accounts ta
            LEFT JOIN bot_instances bi ON ta.bot_instance_id = bi.id
            WHERE ta.customer_id = ?
            ORDER BY ta.created_at DESC
            LIMIT 1
        """, (customer_id,), one=True)
    
    @staticmethod
    def get_expiring_trials(days_ahead: int = 1) -> List[Dict]:
        """Get trials expiring in specified days"""
        
        target_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        return query_db("""
            SELECT ta.*, c.user_id, c.first_name, c.username, bi.bot_username
            FROM trial_accounts ta
            JOIN customers c ON ta.customer_id = c.id
            LEFT JOIN bot_instances bi ON ta.bot_instance_id = bi.id
            WHERE ta.status = 'active' 
            AND DATE(ta.expires_at) = ?
        """, (target_date,))
    
    @staticmethod
    def get_expired_trials() -> List[Dict]:
        """Get trials that have expired"""
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        return query_db("""
            SELECT ta.*, c.user_id, c.first_name, c.username, bi.bot_username
            FROM trial_accounts ta
            JOIN customers c ON ta.customer_id = c.id
            LEFT JOIN bot_instances bi ON ta.bot_instance_id = bi.id
            WHERE ta.status = 'active' 
            AND DATE(ta.expires_at) < ?
        """, (today,))
    
    @staticmethod
    def convert_trial_to_subscription(trial_id: int, subscription_id: int) -> bool:
        """Convert trial to paid subscription"""
        
        try:
            execute_db("""
                UPDATE trial_accounts 
                SET status = 'converted', converted_to_subscription_id = ?
                WHERE id = ?
            """, (subscription_id, trial_id))
            
            # Mark subscription as trial converted
            execute_db("""
                UPDATE subscriptions 
                SET trial_converted = 1
                WHERE id = ?
            """, (subscription_id,))
            
            logger.info(f"Converted trial {trial_id} to subscription {subscription_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error converting trial: {e}")
            return False
    
    @staticmethod
    def expire_trial(trial_id: int) -> bool:
        """Mark trial as expired"""
        
        try:
            execute_db("""
                UPDATE trial_accounts 
                SET status = 'expired'
                WHERE id = ?
            """, (trial_id,))
            
            logger.info(f"Expired trial {trial_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error expiring trial: {e}")
            return False

class TrialNotificationManager:
    """Manages trial notifications"""
    
    @staticmethod
    async def send_trial_welcome(bot, customer_info: Dict, trial_info: Dict):
        """Send welcome message for new trial"""
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode
        
        try:
            message = f"""
🎉 **تست رایگان فعال شد!**

🤖 **ربات شما:** @{trial_info['bot_username']}
👤 **نام کاربری VPN:** `{trial_info['vpn_username']}`
⏳ **مدت تست:** {trial_info['trial_days']} روز
📊 **حجم مجاز:** {trial_info['traffic_limit_gb']} گیگابایت
📅 **تاریخ انقضا:** {trial_info['expires_at'][:10]}

💡 **نکات مهم:**
• از ربات خود برای دریافت کانفیگ استفاده کنید
• حجم و زمان محدود است
• پس از اتمام تست می‌توانید خرید کنید

🎁 **کد تخفیف ویژه:** `TRIAL20` (20% تخفیف)
"""
            
            keyboard = [
                [InlineKeyboardButton("🤖 ورود به ربات", url=f"https://t.me/{trial_info['bot_username']}")],
                [InlineKeyboardButton("🛒 خرید پس از تست", callback_data="convert_trial")]
            ]
            
            await bot.send_message(
                chat_id=customer_info['user_id'],
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Failed to send trial welcome: {e}")
    
    @staticmethod
    async def send_trial_expiry_warning(bot, trial_info: Dict, days_left: int):
        """Send trial expiry warning"""
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.constants import ParseMode
        
        try:
            if days_left > 0:
                message = f"""
⏰ **یادآوری پایان تست رایگان**

🤖 **ربات:** @{trial_info['bot_username']}
⏳ **باقی‌مانده:** {days_left} روز
📊 **حجم باقی‌مانده:** در ربات خود چک کنید

🎁 **تخفیف ویژه برای تبدیل:** 20% با کد `TRIAL20`

برای ادامه استفاده، پلن مناسب خود را انتخاب کنید:
"""
            else:
                message = f"""
🚨 **تست رایگان پایان یافت**

🤖 **ربات:** @{trial_info['bot_username']}
❌ **وضعیت:** منقضی شده

برای ادامه استفاده از سرویس، لطفا خرید کنید:
"""
            
            keyboard = [
                [InlineKeyboardButton("🛒 خرید پلن ماهانه", callback_data="buy_monthly")],
                [InlineKeyboardButton("🛒 خرید پلن سالانه", callback_data="buy_yearly")],
                [InlineKeyboardButton("🎁 استفاده از کد تخفیف", callback_data="apply_trial_discount")]
            ]
            
            await bot.send_message(
                chat_id=trial_info['user_id'],
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Failed to send trial expiry warning: {e}")

class TrialAnalytics:
    """Analytics for trial system"""
    
    @staticmethod
    def get_trial_statistics() -> Dict:
        """Get comprehensive trial statistics"""
        
        # Basic counts
        total_trials = query_db("SELECT COUNT(*) as count FROM trial_accounts", one=True)
        active_trials = query_db("SELECT COUNT(*) as count FROM trial_accounts WHERE status = 'active'", one=True)
        expired_trials = query_db("SELECT COUNT(*) as count FROM trial_accounts WHERE status = 'expired'", one=True)
        converted_trials = query_db("SELECT COUNT(*) as count FROM trial_accounts WHERE status = 'converted'", one=True)
        
        # Conversion rate
        conversion_rate = 0
        if total_trials['count'] > 0:
            conversion_rate = round((converted_trials['count'] / total_trials['count']) * 100, 2)
        
        # Recent trials (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        recent_trials = query_db("""
            SELECT COUNT(*) as count FROM trial_accounts 
            WHERE created_at >= ?
        """, (week_ago,), one=True)
        
        # Average trial duration before conversion
        avg_conversion_time = query_db("""
            SELECT AVG(
                JULIANDAY(s.created_at) - JULIANDAY(ta.created_at)
            ) as avg_days
            FROM trial_accounts ta
            JOIN subscriptions s ON ta.converted_to_subscription_id = s.id
            WHERE ta.status = 'converted'
        """, one=True)
        
        return {
            'total_trials': total_trials['count'],
            'active_trials': active_trials['count'],
            'expired_trials': expired_trials['count'],
            'converted_trials': converted_trials['count'],
            'conversion_rate': conversion_rate,
            'recent_trials': recent_trials['count'],
            'avg_conversion_days': round(avg_conversion_time['avg_days'] or 0, 1)
        }
    
    @staticmethod
    def get_trial_conversion_funnel() -> Dict:
        """Get trial conversion funnel data"""
        
        # Trial starts
        trial_starts = query_db("SELECT COUNT(*) as count FROM trial_accounts", one=True)
        
        # Trial activations (actually used the bot)
        # This would require bot usage data - placeholder for now
        trial_activations = trial_starts  # Assuming all trials are activated
        
        # Purchase attempts (started purchase process)
        purchase_attempts = query_db("""
            SELECT COUNT(DISTINCT ta.customer_id) as count
            FROM trial_accounts ta
            JOIN payments p ON ta.customer_id = p.customer_id
            WHERE p.created_at > ta.created_at
        """, one=True)
        
        # Successful conversions
        conversions = query_db("SELECT COUNT(*) as count FROM trial_accounts WHERE status = 'converted'", one=True)
        
        return {
            'trial_starts': trial_starts['count'],
            'trial_activations': trial_activations['count'],
            'purchase_attempts': purchase_attempts['count'],
            'conversions': conversions['count']
        }

# Initialize managers
trial_manager = TrialManager()
trial_notifications = TrialNotificationManager()
trial_analytics = TrialAnalytics()