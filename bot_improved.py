# -*- coding: utf-8 -*-
"""
Enhanced VPN Telegram Bot
A secure and feature-rich Telegram bot for selling VPN configurations
"""

import asyncio
import logging
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters, TypeHandler, ApplicationHandlerStop
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError, Forbidden, BadRequest

# Import our modules
from config import config, States
from database import db_manager, query_db, execute_db, user_repo
from marzban_api import VpnPanelAPI, bytes_to_gb
from validators import (
    validator, security, rate_limiter, check_rate_limit,
    validate_plan_data, validate_discount_data, validate_panel_data,
    ValidationError as CustomValidationError
)

# Setup logging
logger = logging.getLogger(__name__)

class BotError(Exception):
    """Base exception for bot errors"""
    pass

class SecurityMiddleware:
    """Security middleware for the bot"""
    
    @staticmethod
    async def check_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check user permissions and rate limits"""
        user = update.effective_user
        if not user:
            return False
        
        # Check rate limit
        if not check_rate_limit(user.id):
            if update.callback_query:
                await update.callback_query.answer(
                    "شما خیلی سریع درخواست می‌فرستید. لطفا کمی صبر کنید.", 
                    show_alert=True
                )
            elif update.message:
                await update.message.reply_text(
                    "⚠️ تعداد درخواست‌های شما بیش از حد مجاز است. لطفا کمی صبر کنید."
                )
            return False
        
        return True
    
    @staticmethod
    async def force_join_checker(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user has joined the required channel"""
        user = update.effective_user
        if not user or user.id == config.ADMIN_ID:
            return True
        
        try:
            member = await context.bot.get_chat_member(
                chat_id=config.CHANNEL_ID, 
                user_id=user.id
            )
            if member.status in ['member', 'administrator', 'creator']:
                return True
        except TelegramError as e:
            logger.warning(f"Could not check channel membership for {user.id}: {e}")
            return True  # Allow access if we can't check
        
        # User hasn't joined - show join message
        join_url = f"https://t.me/{config.CHANNEL_USERNAME.replace('@', '')}"
        keyboard = [
            [InlineKeyboardButton("🔗 عضویت در کانال", url=join_url)],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]
        ]
        text = (
            "⚠️ **قفل عضویت**\n\n"
            "برای استفاده از ربات، ابتدا در کانال ما عضو شوید و سپس دکمه «عضو شدم» را بزنید."
        )
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN
            )
            await update.callback_query.answer("شما هنوز در کانال عضو نیستید!", show_alert=True)
        elif update.message:
            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN
            )
        
        return False

class UserManager:
    """User management operations"""
    
    @staticmethod
    async def register_user(user):
        """Register a new user"""
        if not user_repo.user_exists(user.id):
            success = user_repo.create_user(user.id, user.first_name)
            if success:
                logger.info(f"Registered new user {user.id} ({user.first_name})")
            return success
        return True

class MessageManager:
    """Dynamic message management"""
    
    @staticmethod
    async def send_dynamic_message(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                 message_name: str, back_to: str = 'start_main', **kwargs):
        """Send a dynamic message with buttons"""
        query = update.callback_query
        
        message_data = query_db(
            "SELECT text, file_id, file_type FROM messages WHERE message_name = ?", 
            (message_name,), one=True
        )
        
        if not message_data:
            if query:
                await query.answer(f"محتوای '{message_name}' یافت نشد!", show_alert=True)
            return
        
        text = message_data.get('text', '')
        file_id = message_data.get('file_id')
        file_type = message_data.get('file_type')
        
        # Format text with provided kwargs
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format key in message {message_name}: {e}")
        
        # Get buttons
        buttons_data = query_db(
            "SELECT text, target, is_url, row, col FROM buttons WHERE menu_name = ? ORDER BY row, col", 
            (message_name,)
        )
        
        # Filter buttons based on settings (e.g., trial status)
        if message_name == 'start_main':
            trial_status = query_db("SELECT value FROM settings WHERE key = 'free_trial_status'", one=True)
            if not trial_status or trial_status.get('value') != '1':
                buttons_data = [b for b in buttons_data if b.get('target') != 'get_free_config']
        
        # Build keyboard
        keyboard = MessageManager._build_keyboard(buttons_data, message_name, back_to)
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Send message
        await MessageManager._send_message(query, text, file_id, file_type, reply_markup)
    
    @staticmethod
    def _build_keyboard(buttons_data, message_name, back_to):
        """Build keyboard from button data"""
        if not buttons_data:
            return []
        
        keyboard = []
        max_row = max((b['row'] for b in buttons_data), default=0)
        keyboard_rows = [[] for _ in range(max_row + 1)]
        
        for b in buttons_data:
            if b['is_url']:
                btn = InlineKeyboardButton(b['text'], url=b['target'])
            else:
                btn = InlineKeyboardButton(b['text'], callback_data=b['target'])
            
            if 0 < b['row'] <= len(keyboard_rows):
                keyboard_rows[b['row'] - 1].append(btn)
        
        keyboard = [row for row in keyboard_rows if row]
        
        # Add back button if not main menu
        if message_name != 'start_main':
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=back_to)])
        
        return keyboard
    
    @staticmethod
    async def _send_message(query, text, file_id, file_type, reply_markup):
        """Send message with proper media handling"""
        try:
            if file_id and file_type:
                # Delete current message if it has media
                if query.message and (query.message.photo or query.message.video or query.message.document):
                    await query.message.delete()
                
                # Send new message with media
                sender = getattr(query.from_user.get_bot(), f"send_{file_type}")
                await sender(
                    chat_id=query.message.chat_id,
                    **{file_type: file_id},
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # Edit text message
                await query.message.edit_text(
                    text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN
                )
        except TelegramError as e:
            if 'Message is not modified' not in str(e):
                logger.error(f"Error sending dynamic message: {e}")

class BotHandlers:
    """Main bot handlers"""
    
    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /start command"""
        # Security checks
        if not await SecurityMiddleware.check_permissions(update, context):
            return ConversationHandler.END
        
        if not await SecurityMiddleware.force_join_checker(update, context):
            raise ApplicationHandlerStop
        
        # Register user
        await UserManager.register_user(update.effective_user)
        context.user_data.clear()
        
        # Send main menu
        await MessageManager.send_dynamic_message(update, context, 'start_main')
        return ConversationHandler.END
    
    @staticmethod
    async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /admin command"""
        if not security.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
            return ConversationHandler.END
        
        await MessageManager.send_dynamic_message(update, context, 'admin_panel_main')
        return States.ADMIN_MAIN_MENU
    
    @staticmethod
    async def get_free_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free config request"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Check if user already got free trial
        if query_db("SELECT 1 FROM free_trials WHERE user_id = ?", (user_id,), one=True):
            await query.answer("شما قبلاً کانفیگ تست خود را دریافت کرده‌اید.", show_alert=True)
            return
        
        # Get first available panel
        first_panel = query_db("SELECT id FROM panels WHERE is_active = 1 ORDER BY id LIMIT 1", one=True)
        if not first_panel:
            await query.message.edit_text(
                "❌ متاسفانه هیچ پنلی برای ارائه سرویس تنظیم نشده است.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data='start_main')
                ]])
            )
            return
        
        try:
            await query.message.edit_text("لطفا کمی صبر کنید... ⏳")
            
            # Get trial settings
            settings = {
                s['key']: s['value'] 
                for s in query_db("SELECT key, value FROM settings WHERE key LIKE 'free_trial_%'")
            }
            
            trial_plan = {
                'traffic_gb': settings.get('free_trial_gb', '0.2'),
                'duration_days': settings.get('free_trial_days', '1')
            }
            
            # Create user in panel
            panel_api = VpnPanelAPI(panel_id=first_panel['id'])
            marzban_username, config_link, message = await panel_api.create_user(user_id, trial_plan)
            
            if config_link:
                # Save order
                plan_id = query_db("SELECT id FROM plans LIMIT 1", one=True)
                plan_id = plan_id['id'] if plan_id else -1
                
                execute_db(
                    "INSERT INTO orders (user_id, plan_id, panel_id, status, marzban_username, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, plan_id, first_panel['id'], 'approved', marzban_username, datetime.now().isoformat())
                )
                
                execute_db(
                    "INSERT INTO free_trials (user_id, timestamp) VALUES (?, ?)",
                    (user_id, datetime.now().isoformat())
                )
                
                text = (
                    f"✅ کانفیگ تست رایگان شما با موفقیت ساخته شد!\n\n"
                    f"<b>حجم:</b> {trial_plan['traffic_gb']} گیگابایت\n"
                    f"<b>مدت اعتبار:</b> {trial_plan['duration_days']} روز\n\n"
                    f"لینک کانفیگ شما:\n<code>{config_link}</code>\n\n"
                    f"<b>آموزش اتصال:</b>\nhttps://t.me/madeingod_tm"
                )
                
                await query.message.edit_text(
                    text, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت به منو", callback_data='start_main')
                    ]])
                )
            else:
                await query.message.edit_text(
                    f"❌ متاسفانه در حال حاضر امکان ارائه کانفیگ تست وجود ندارد.\nخطا: {message}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت به منو", callback_data='start_main')
                    ]])
                )
                
        except Exception as e:
            logger.error(f"Error in free config handler: {e}")
            await query.message.edit_text(
                "❌ خطای داخلی. لطفا بعداً تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data='start_main')
                ]])
            )
    
    @staticmethod
    async def my_services_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle my services request"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        orders = query_db(
            "SELECT id, marzban_username, plan_id FROM orders WHERE user_id = ? AND status = 'approved' AND marzban_username IS NOT NULL ORDER BY id DESC",
            (user_id,)
        )
        
        if not orders:
            await query.message.edit_text(
                "شما در حال حاضر هیچ سرویس فعالی ندارید.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data='start_main')
                ]])
            )
            return
        
        keyboard = []
        text = "سرویس‌های فعال شما:"
        
        for order in orders:
            plan = query_db("SELECT name FROM plans WHERE id = ?", (order['plan_id'],), one=True)
            plan_name = plan['name'] if plan else "سرویس تست/ویژه"
            button_text = f"{plan_name} ({order['marzban_username']})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_service_{order['id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='start_main')])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    @staticmethod
    async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle join check callback"""
        if await SecurityMiddleware.force_join_checker(update, context):
            await UserManager.register_user(update.effective_user)
            await BotHandlers.start_command(update, context)
    
    @staticmethod
    async def dynamic_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle dynamic buttons"""
        query = update.callback_query
        
        # Reserved prefixes that should not be handled by dynamic handler
        RESERVED_PREFIXES = [
            'approve_', 'reject_', 'plan_', 'select_plan_', 'card_', 'msg_', 'edit_plan_',
            'btn_', 'noop_', 'renew_', 'set_', 'delete_discount_', 'add_discount_code',
            'panel_', 'backup_', 'admin_', 'apply_discount_start', 'confirm_purchase',
            'get_free_config', 'my_services', 'view_service_', 'check_join', 'buy_config_main',
            'inbound_'
        ]
        
        if any(query.data.startswith(p) for p in RESERVED_PREFIXES):
            return
        
        await query.answer()
        message_name = query.data
        
        if query_db("SELECT 1 FROM messages WHERE message_name = ?", (message_name,), one=True):
            await MessageManager.send_dynamic_message(update, context, message_name=message_name)
        else:
            logger.warning(f"Unhandled dynamic callback from user {query.from_user.id}: {message_name}")
            await query.answer("این دکمه در حال حاضر کار نمی‌کند.", show_alert=True)

class ScheduledTasks:
    """Scheduled tasks for the bot"""
    
    @staticmethod
    async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
        """Check for service expirations and send reminders"""
        logger.info("Running daily expiration check job...")
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        reminder_msg_data = query_db(
            "SELECT text FROM messages WHERE message_name = 'renewal_reminder_text'", 
            one=True
        )
        
        if not reminder_msg_data:
            logger.error("Renewal reminder message template not found. Skipping job.")
            return
        
        reminder_template = reminder_msg_data['text']
        
        # Get active orders
        active_orders = query_db(
            "SELECT id, user_id, marzban_username, panel_id, last_reminder_date "
            "FROM orders WHERE status = 'approved' AND marzban_username IS NOT NULL AND panel_id IS NOT NULL"
        )
        
        # Group orders by username for efficiency
        orders_map = {}
        for order in active_orders:
            username = order['marzban_username']
            if username not in orders_map:
                orders_map[username] = []
            orders_map[username].append(order)
        
        # Check each panel
        panels = query_db("SELECT id FROM panels WHERE is_active = 1")
        for panel_data in panels:
            try:
                panel_api = VpnPanelAPI(panel_id=panel_data['id'])
                users, msg = await panel_api.get_all_users()
                
                if not users:
                    logger.warning(f"Skipping panel {panel_data['id']} due to error: {msg}")
                    continue
                
                for user in users:
                    username = user.get('username')
                    if username not in orders_map:
                        continue
                    
                    user_orders = orders_map[username]
                    for order in user_orders:
                        # Skip if already reminded today
                        if order['last_reminder_date'] == today_str:
                            continue
                        
                        reminder_needed = False
                        details_str = ""
                        
                        # Check time-based expiry
                        if user.get('expire'):
                            expire_dt = datetime.fromtimestamp(user['expire'])
                            days_left = (expire_dt - datetime.now()).days
                            
                            if 0 <= days_left <= 3:
                                reminder_needed = True
                                details_str = f"تنها **{days_left + 1} روز** تا پایان اعتبار زمانی سرویس شما باقی مانده است."
                        
                        # Check usage-based limit
                        if not reminder_needed and user.get('data_limit', 0) > 0:
                            usage_percent = (user.get('used_traffic', 0) / user['data_limit']) * 100
                            if usage_percent >= 80:
                                reminder_needed = True
                                details_str = f"بیش از **{int(usage_percent)} درصد** از حجم سرویس شما مصرف شده است."
                        
                        # Send reminder if needed
                        if reminder_needed:
                            try:
                                final_msg = reminder_template.format(
                                    marzban_username=username,
                                    details=details_str
                                )
                                
                                await context.bot.send_message(
                                    order['user_id'], final_msg, parse_mode=ParseMode.MARKDOWN
                                )
                                
                                execute_db(
                                    "UPDATE orders SET last_reminder_date = ? WHERE id = ?",
                                    (today_str, order['id'])
                                )
                                
                                logger.info(f"Sent reminder to user {order['user_id']} for service {username}")
                                
                            except (Forbidden, BadRequest):
                                logger.warning(f"Could not send reminder to blocked user {order['user_id']}")
                            except Exception as e:
                                logger.error(f"Error sending reminder to {order['user_id']}: {e}")
                            
                            await asyncio.sleep(0.5)  # Rate limiting
                            
            except Exception as e:
                logger.error(f"Failed to process reminders for panel {panel_data['id']}: {e}")

def create_application() -> Application:
    """Create and configure the bot application"""
    # Create application
    application = Application.builder().token(config.BOT_TOKEN).build()
    
    # Add job queue for scheduled tasks
    if application.job_queue:
        application.job_queue.run_daily(
            ScheduledTasks.check_expirations,
            time=time(hour=9, minute=0, second=0),
            name="daily_expiration_check"
        )
    
    # Add security middleware
    application.add_handler(
        TypeHandler(Update, SecurityMiddleware.check_permissions), 
        group=-1
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', BotHandlers.start_command))
    application.add_handler(CommandHandler('admin', BotHandlers.admin_command))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(
        BotHandlers.get_free_config_handler, pattern=r'^get_free_config$'
    ))
    application.add_handler(CallbackQueryHandler(
        BotHandlers.my_services_handler, pattern=r'^my_services$'
    ))
    application.add_handler(CallbackQueryHandler(
        BotHandlers.check_join_callback, pattern='^check_join$'
    ))
    application.add_handler(CallbackQueryHandler(
        BotHandlers.start_command, pattern='^start_main$'
    ))
    
    # Dynamic button handler (should be last)
    application.add_handler(CallbackQueryHandler(BotHandlers.dynamic_button_handler))
    
    return application

def main():
    """Main function to run the bot"""
    try:
        logger.info("Starting VPN Telegram Bot...")
        logger.info(f"Bot configuration: Admin ID = {config.ADMIN_ID}")
        
        # Create and run application
        application = create_application()
        
        logger.info("Bot is running... Press Ctrl+C to stop.")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        logger.info("Bot shutdown complete")

if __name__ == "__main__":
    main()