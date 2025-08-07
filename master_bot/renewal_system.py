# -*- coding: utf-8 -*-
"""
Automatic Renewal System for Master Bot
Handles subscription renewals, notifications, and payment processing
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
from telegram import Bot
from telegram.constants import ParseMode

from database import execute_db, query_db, customer_repo, subscription_repo
from payment import payment_service
from config import config

logger = logging.getLogger(__name__)

class RenewalNotificationManager:
    """Manages renewal notifications and reminders"""
    
    # Notification schedules (days before expiry)
    NOTIFICATION_SCHEDULE = [7, 3, 1]
    
    @staticmethod
    def get_expiring_subscriptions(days_ahead: int = 7) -> List[Dict]:
        """Get subscriptions expiring in specified days"""
        
        target_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')
        
        return query_db("""
            SELECT s.*, c.user_id, c.first_name, c.username, 
                   bi.bot_username, bi.container_name
            FROM subscriptions s
            JOIN customers c ON s.customer_id = c.id
            JOIN bot_instances bi ON s.bot_instance_id = bi.id
            WHERE s.status = 'active' 
            AND DATE(s.expires_at) = ?
            AND s.auto_renewal_enabled = 1
        """, (target_date,))
    
    @staticmethod
    def get_expired_subscriptions() -> List[Dict]:
        """Get subscriptions that have expired"""
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        return query_db("""
            SELECT s.*, c.user_id, c.first_name, c.username, 
                   bi.bot_username, bi.container_name
            FROM subscriptions s
            JOIN customers c ON s.customer_id = c.id
            JOIN bot_instances bi ON s.bot_instance_id = bi.id
            WHERE s.status = 'active' 
            AND DATE(s.expires_at) < ?
        """, (today,))
    
    @staticmethod
    async def send_renewal_reminder(bot: Bot, subscription: Dict, days_left: int):
        """Send renewal reminder to customer"""
        
        try:
            plan_text = "ماهانه" if subscription['plan_type'] == 'monthly' else "سالانه"
            
            if days_left > 0:
                message = f"""
⏰ **یادآوری تمدید اشتراک**

🤖 **ربات:** @{subscription['bot_username']}
📦 **پلن:** {plan_text}
⏳ **باقی‌مانده:** {days_left} روز
💰 **قیمت تمدید:** {subscription['price']:,} تومان

🎁 **تخفیف ویژه تمدید:** 15% با کد `RENEW15`

برای تمدید روی دکمه زیر کلیک کنید:
"""
            else:
                message = f"""
🚨 **اشتراک منقضی شده**

🤖 **ربات:** @{subscription['bot_username']}
📦 **پلن:** {plan_text}
❌ **وضعیت:** منقضی شده

برای تمدید فوری کلیک کنید:
"""
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            keyboard = [
                [InlineKeyboardButton("🔄 تمدید فوری", callback_data=f"renew_{subscription['id']}")],
                [InlineKeyboardButton("⚙️ تنظیمات تمدید خودکار", callback_data=f"auto_renew_settings_{subscription['id']}")]
            ]
            
            await bot.send_message(
                chat_id=subscription['user_id'],
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            logger.info(f"Sent renewal reminder to user {subscription['user_id']} for subscription {subscription['id']}")
            
        except Exception as e:
            logger.error(f"Failed to send renewal reminder: {e}")
    
    @staticmethod
    async def send_renewal_success(bot: Bot, subscription: Dict):
        """Send renewal success notification"""
        
        try:
            plan_text = "ماهانه" if subscription['plan_type'] == 'monthly' else "سالانه"
            
            message = f"""
✅ **تمدید موفق**

🤖 **ربات:** @{subscription['bot_username']}
📦 **پلن:** {plan_text}
💰 **مبلغ:** {subscription['price']:,} تومان
📅 **تاریخ انقضا:** {subscription['expires_at']}

🎉 اشتراک شما با موفقیت تمدید شد!
"""
            
            await bot.send_message(
                chat_id=subscription['user_id'],
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Failed to send renewal success notification: {e}")

class AutoRenewalProcessor:
    """Processes automatic renewals"""
    
    @staticmethod
    def get_auto_renewal_subscriptions() -> List[Dict]:
        """Get subscriptions eligible for auto renewal"""
        
        # Get subscriptions expiring today with auto renewal enabled
        today = datetime.now().strftime('%Y-%m-%d')
        
        return query_db("""
            SELECT s.*, c.user_id, c.first_name, c.username,
                   pm.method as payment_method, pm.card_id, pm.wallet_id
            FROM subscriptions s
            JOIN customers c ON s.customer_id = c.id
            LEFT JOIN payment_methods pm ON s.customer_id = pm.customer_id AND pm.is_default = 1
            WHERE s.status = 'active' 
            AND DATE(s.expires_at) = ?
            AND s.auto_renewal_enabled = 1
        """, (today,))
    
    @staticmethod
    async def process_auto_renewal(bot: Bot, subscription: Dict) -> bool:
        """Process automatic renewal for a subscription"""
        
        try:
            # Check if customer has default payment method
            if not subscription.get('payment_method'):
                await AutoRenewalProcessor._notify_renewal_failed(
                    bot, subscription, "روش پرداخت پیش‌فرض تنظیم نشده"
                )
                return False
            
            # Create renewal payment
            payment_data = {
                'customer_id': subscription['customer_id'],
                'amount': subscription['price'],
                'method': subscription['payment_method'],
                'description': f"تمدید خودکار - {subscription['plan_type']}",
                'subscription_id': subscription['id']
            }
            
            # Process payment
            payment_result = await payment_service.create_payment(payment_data)
            
            if payment_result.get('success'):
                # Extend subscription
                new_expiry = AutoRenewalProcessor._calculate_new_expiry(
                    subscription['expires_at'], 
                    subscription['plan_type']
                )
                
                execute_db("""
                    UPDATE subscriptions 
                    SET expires_at = ?, renewed_count = renewed_count + 1
                    WHERE id = ?
                """, (new_expiry, subscription['id']))
                
                # Send success notification
                subscription['expires_at'] = new_expiry
                await RenewalNotificationManager.send_renewal_success(bot, subscription)
                
                logger.info(f"Auto renewal successful for subscription {subscription['id']}")
                return True
            else:
                await AutoRenewalProcessor._notify_renewal_failed(
                    bot, subscription, payment_result.get('error', 'خطا در پردازش پرداخت')
                )
                return False
                
        except Exception as e:
            logger.error(f"Auto renewal failed for subscription {subscription['id']}: {e}")
            await AutoRenewalProcessor._notify_renewal_failed(
                bot, subscription, "خطای سیستمی"
            )
            return False
    
    @staticmethod
    def _calculate_new_expiry(current_expiry: str, plan_type: str) -> str:
        """Calculate new expiry date"""
        
        current_date = datetime.fromisoformat(current_expiry)
        
        if plan_type == 'monthly':
            new_date = current_date + timedelta(days=30)
        else:  # yearly
            new_date = current_date + timedelta(days=365)
        
        return new_date.isoformat()
    
    @staticmethod
    async def _notify_renewal_failed(bot: Bot, subscription: Dict, reason: str):
        """Notify customer about failed auto renewal"""
        
        try:
            message = f"""
❌ **خطا در تمدید خودکار**

🤖 **ربات:** @{subscription.get('bot_username', 'نامشخص')}
❗ **علت:** {reason}

لطفا برای تمدید دستی اقدام کنید:
"""
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            
            keyboard = [
                [InlineKeyboardButton("🔄 تمدید دستی", callback_data=f"manual_renew_{subscription['id']}")],
                [InlineKeyboardButton("💳 تغییر روش پرداخت", callback_data=f"change_payment_method_{subscription['id']}")]
            ]
            
            await bot.send_message(
                chat_id=subscription['user_id'],
                text=message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Failed to send renewal failed notification: {e}")

class RenewalScheduler:
    """Schedules and manages renewal tasks"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.notification_manager = RenewalNotificationManager()
        self.renewal_processor = AutoRenewalProcessor()
    
    async def run_daily_renewal_check(self):
        """Run daily renewal check - should be called by scheduler"""
        
        logger.info("Starting daily renewal check...")
        
        try:
            # Send renewal reminders
            for days in self.notification_manager.NOTIFICATION_SCHEDULE:
                expiring_subs = self.notification_manager.get_expiring_subscriptions(days)
                
                for sub in expiring_subs:
                    await self.notification_manager.send_renewal_reminder(self.bot, sub, days)
                    await asyncio.sleep(0.1)  # Rate limiting
            
            # Process auto renewals
            auto_renewal_subs = self.renewal_processor.get_auto_renewal_subscriptions()
            
            renewal_stats = {'success': 0, 'failed': 0}
            
            for sub in auto_renewal_subs:
                success = await self.renewal_processor.process_auto_renewal(self.bot, sub)
                if success:
                    renewal_stats['success'] += 1
                else:
                    renewal_stats['failed'] += 1
                
                await asyncio.sleep(0.5)  # Rate limiting
            
            # Mark expired subscriptions
            expired_subs = self.notification_manager.get_expired_subscriptions()
            
            for sub in expired_subs:
                execute_db("""
                    UPDATE subscriptions 
                    SET status = 'expired' 
                    WHERE id = ?
                """, (sub['id'],))
                
                # Send expiry notification
                await self.notification_manager.send_renewal_reminder(self.bot, sub, 0)
            
            # Send admin report
            await self._send_admin_report(renewal_stats, len(expired_subs))
            
            logger.info(f"Daily renewal check completed. Renewals: {renewal_stats['success']} success, {renewal_stats['failed']} failed, {len(expired_subs)} expired")
            
        except Exception as e:
            logger.error(f"Error in daily renewal check: {e}")
    
    async def _send_admin_report(self, renewal_stats: Dict, expired_count: int):
        """Send daily renewal report to admin"""
        
        try:
            report = f"""
📊 **گزارش روزانه تمدید**

🔄 **تمدید خودکار:**
• موفق: {renewal_stats['success']} مورد
• ناموفق: {renewal_stats['failed']} مورد

⏰ **اشتراک‌های منقضی شده:** {expired_count} مورد

📅 **تاریخ:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
            
            await self.bot.send_message(
                chat_id=config.MASTER_ADMIN_ID,
                text=report,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Failed to send admin report: {e}")

# Initialize renewal scheduler
renewal_scheduler = None

def initialize_renewal_scheduler(bot: Bot):
    """Initialize renewal scheduler with bot instance"""
    global renewal_scheduler
    renewal_scheduler = RenewalScheduler(bot)
    return renewal_scheduler