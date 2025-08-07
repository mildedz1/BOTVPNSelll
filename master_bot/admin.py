# -*- coding: utf-8 -*-
"""
Admin Panel for Master Bot
Manages payment methods, prices, and system settings
"""

import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import config, States
from database import execute_db, query_db, customer_repo, subscription_repo
from payment import payment_service

logger = logging.getLogger(__name__)

class AdminHandlers:
    """Admin panel handlers"""
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == config.MASTER_ADMIN_ID
    
    @staticmethod
    async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin main panel"""
        user = update.effective_user
        
        if not AdminHandlers.is_admin(user.id):
            await update.message.reply_text("❌ شما به این بخش دسترسی ندارید.")
            return
        
        # Get statistics
        total_customers = len(customer_repo.get_all_customers())
        active_subscriptions = len(subscription_repo.get_active_subscriptions())
        pending_payments = len(payment_service.get_pending_payments())
        
        total_revenue = query_db("""
            SELECT COALESCE(SUM(amount), 0) as total 
            FROM payments WHERE status = 'paid'
        """, one=True)['total']
        
        admin_text = f"""
🔧 **پنل مدیریت Master Bot**

📊 **آمار کلی:**
👥 کل مشتریان: {total_customers:,}
📦 اشتراکات فعال: {active_subscriptions:,}
⏳ پرداخت‌های در انتظار: {pending_payments:,}
💰 کل درآمد: {total_revenue:,} تومان

⚙️ **مدیریت سیستم:**
"""
        
        keyboard = [
            [
                InlineKeyboardButton("💳 مدیریت کارت‌ها", callback_data="admin_cards"),
                InlineKeyboardButton("🪙 مدیریت ولت‌ها", callback_data="admin_wallets")
            ],
            [
                InlineKeyboardButton("⚙️ تنظیمات پرداخت", callback_data="admin_payment_settings"),
                InlineKeyboardButton("💵 تنظیم قیمت دلار", callback_data="admin_dollar_price")
            ],
            [
                InlineKeyboardButton("✅ تایید پرداخت‌ها", callback_data="admin_verify_payments"),
                InlineKeyboardButton("📊 گزارشات", callback_data="admin_reports")
            ],
            [
                InlineKeyboardButton("👥 مدیریت مشتریان", callback_data="admin_customers"),
                InlineKeyboardButton("🔧 تنظیمات سیستم", callback_data="admin_system_settings")
            ]
        ]
        
        if update.message:
            await update.message.reply_text(
                admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.callback_query.edit_message_text(
                admin_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
    
    @staticmethod
    async def manage_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage payment cards"""
        query = update.callback_query
        await query.answer()
        
        cards = query_db("SELECT * FROM payment_cards ORDER BY priority ASC, id ASC")
        
        text = "💳 **مدیریت کارت‌های بانکی**\n\n"
        keyboard = []
        
        if cards:
            for card in cards:
                status_emoji = "✅" if card['is_active'] else "❌"
                text += f"{status_emoji} **{card['card_name']}**\n"
                text += f"   💳 {card['card_number']}\n"
                text += f"   🏦 {card.get('bank_name', 'نامشخص')}\n"
                text += f"   📊 اولویت: {card['priority']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"ویرایش {card['card_name']}", callback_data=f"edit_card_{card['id']}")
                ])
        else:
            text += "📭 هیچ کارتی تعریف نشده است.\n\n"
        
        keyboard.extend([
            [InlineKeyboardButton("➕ افزودن کارت جدید", callback_data="add_card")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def manage_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage crypto wallets"""
        query = update.callback_query
        await query.answer()
        
        wallets = query_db("SELECT * FROM crypto_wallets ORDER BY priority ASC, id ASC")
        
        text = "🪙 **مدیریت کیف پول‌های رمز ارز**\n\n"
        keyboard = []
        
        if wallets:
            for wallet in wallets:
                status_emoji = "✅" if wallet['is_active'] else "❌"
                text += f"{status_emoji} **{wallet['crypto_type']}**\n"
                text += f"   🏦 {wallet['wallet_address'][:20]}...\n"
                text += f"   🌐 {wallet.get('network', 'نامشخص')}\n"
                text += f"   📊 اولویت: {wallet['priority']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"ویرایش {wallet['crypto_type']}", callback_data=f"edit_wallet_{wallet['id']}")
                ])
        else:
            text += "📭 هیچ کیف پولی تعریف نشده است.\n\n"
        
        keyboard.extend([
            [InlineKeyboardButton("➕ افزودن کیف پول جدید", callback_data="add_wallet")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def payment_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Payment method settings"""
        query = update.callback_query
        await query.answer()
        
        # Get current settings
        aqay_status = "✅ فعال" if config.AQAY_ENABLED else "❌ غیرفعال"
        card_status = "✅ فعال" if config.CARD_TO_CARD_ENABLED else "❌ غیرفعال"
        crypto_status = "✅ فعال" if config.CRYPTO_ENABLED else "❌ غیرفعال"
        
        text = f"""
⚙️ **تنظیمات روش‌های پرداخت**

🌐 **درگاه آقای پرداخت:** {aqay_status}
💳 **کارت به کارت:** {card_status}
🪙 **رمز ارز:** {crypto_status}

برای تغییر وضعیت هر روش، روی دکمه مربوطه کلیک کنید:
"""
        
        keyboard = [
            [InlineKeyboardButton(f"🌐 آقای پرداخت {aqay_status}", callback_data="toggle_aqay")],
            [InlineKeyboardButton(f"💳 کارت به کارت {card_status}", callback_data="toggle_card_to_card")],
            [InlineKeyboardButton(f"🪙 رمز ارز {crypto_status}", callback_data="toggle_crypto")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def set_dollar_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set dollar price for crypto"""
        query = update.callback_query
        await query.answer()
        
        current_price = query_db("SELECT value FROM settings WHERE key = 'dollar_price'", one=True)
        current_price_value = current_price['value'] if current_price else config.DEFAULT_DOLLAR_PRICE
        
        text = f"""
💵 **تنظیم قیمت دلار**

💰 **قیمت فعلی:** {current_price_value:,} تومان

این قیمت برای محاسبه مبلغ رمز ارز استفاده می‌شود.

لطفا قیمت جدید دلار را به تومان وارد کنید:
مثال: `52000`
"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        context.user_data['admin_action'] = 'set_dollar_price'
        return States.ADMIN_SETTINGS
    
    @staticmethod
    async def verify_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show pending payments for verification"""
        query = update.callback_query
        await query.answer()
        
        pending_payments = payment_service.get_pending_payments()
        
        if not pending_payments:
            text = "✅ **تمام پرداخت‌ها تایید شده‌اند!**\n\nهیچ پرداخت در انتظار تایید وجود ندارد."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]]
        else:
            text = f"⏳ **پرداخت‌های در انتظار تایید** ({len(pending_payments)} مورد)\n\n"
            keyboard = []
            
            for payment in pending_payments[:10]:  # Show max 10 at a time
                method_emoji = "💳" if payment['payment_method'] == 'card_to_card' else "🪙"
                
                text += f"{method_emoji} **کد پرداخت:** {payment['transaction_id']}\n"
                text += f"👤 **مشتری:** {payment['first_name']}"
                if payment['username']:
                    text += f" (@{payment['username']})"
                text += f"\n💰 **مبلغ:** {payment['amount']:,} تومان\n"
                
                if payment['payment_method'] == 'card_to_card':
                    text += f"💳 **کارت:** {payment['card_number']}\n"
                elif payment['payment_method'] == 'crypto':
                    text += f"🪙 **رمز ارز:** {payment['crypto_amount']} {payment['crypto_type']}\n"
                    text += f"🏦 **کیف پول:** {payment['wallet_address'][:20]}...\n"
                
                text += f"📅 **تاریخ:** {payment['created_at'][:16]}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"✅ تایید {payment['transaction_id']}", callback_data=f"approve_payment_{payment['id']}"),
                    InlineKeyboardButton(f"❌ رد {payment['transaction_id']}", callback_data=f"reject_payment_{payment['id']}")
                ])
            
            if len(pending_payments) > 10:
                keyboard.append([InlineKeyboardButton("📄 مشاهده بیشتر", callback_data="more_payments")])
            
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Approve a payment"""
        query = update.callback_query
        await query.answer()
        
        payment_id = int(query.data.split('_')[-1])
        
        # Update payment status
        execute_db("""
            UPDATE payments SET status = 'paid', payment_date = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (payment_id,))
        
        # Get payment info
        payment = query_db("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
        
        if payment:
            # Update customer total_paid
            execute_db("""
                UPDATE customers SET total_paid = total_paid + ? WHERE id = ?
            """, (payment['amount'], payment['customer_id']))
            
            # Get customer info to send notification
            customer = query_db("SELECT * FROM customers WHERE id = ?", (payment['customer_id'],), one=True)
            
            if customer:
                try:
                    # Send notification to customer
                    await context.bot.send_message(
                        chat_id=customer['user_id'],
                        text=f"""
✅ **پرداخت شما تایید شد!**

💰 **مبلغ:** {payment['amount']:,} تومان
🔢 **کد پرداخت:** {payment['transaction_id']}

ربات شما در حال راه‌اندازی است...
                        """,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Failed to send notification to customer: {e}")
            
            await query.edit_message_text(
                f"✅ **پرداخت تایید شد!**\n\n"
                f"کد پرداخت: {payment['transaction_id']}\n"
                f"مبلغ: {payment['amount']:,} تومان\n\n"
                f"اعلان به مشتری ارسال شد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به پرداخت‌ها", callback_data="admin_verify_payments")
                ]])
            )
        else:
            await query.edit_message_text("❌ خطا در تایید پرداخت.")
    
    @staticmethod
    async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Reject a payment"""
        query = update.callback_query
        await query.answer()
        
        payment_id = int(query.data.split('_')[-1])
        
        # Update payment status
        execute_db("UPDATE payments SET status = 'failed' WHERE id = ?", (payment_id,))
        
        # Get payment info
        payment = query_db("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
        
        if payment:
            # Get customer info to send notification
            customer = query_db("SELECT * FROM customers WHERE id = ?", (payment['customer_id'],), one=True)
            
            if customer:
                try:
                    # Send notification to customer
                    await context.bot.send_message(
                        chat_id=customer['user_id'],
                        text=f"""
❌ **پرداخت شما رد شد**

💰 **مبلغ:** {payment['amount']:,} تومان
🔢 **کد پرداخت:** {payment['transaction_id']}

لطفا مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.
                        """,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.error(f"Failed to send notification to customer: {e}")
            
            await query.edit_message_text(
                f"❌ **پرداخت رد شد!**\n\n"
                f"کد پرداخت: {payment['transaction_id']}\n"
                f"مبلغ: {payment['amount']:,} تومان\n\n"
                f"اعلان به مشتری ارسال شد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به پرداخت‌ها", callback_data="admin_verify_payments")
                ]])
            )
        else:
            await query.edit_message_text("❌ خطا در رد پرداخت.")
    
    @staticmethod
    async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin text inputs"""
        if not AdminHandlers.is_admin(update.effective_user.id):
            return
        
        action = context.user_data.get('admin_action')
        
        if action == 'set_dollar_price':
            try:
                new_price = float(update.message.text.strip().replace(',', ''))
                
                if new_price <= 0:
                    await update.message.reply_text("❌ قیمت باید بیشتر از صفر باشد.")
                    return
                
                # Update dollar price in settings
                execute_db("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at) 
                    VALUES ('dollar_price', ?, CURRENT_TIMESTAMP)
                """, (str(new_price),))
                
                await update.message.reply_text(
                    f"✅ **قیمت دلار بروزرسانی شد!**\n\n"
                    f"💰 **قیمت جدید:** {new_price:,} تومان",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت به پنل ادمین", callback_data="admin_panel")
                    ]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                
                context.user_data.clear()
                
            except ValueError:
                await update.message.reply_text(
                    "❌ لطفا عدد معتبر وارد کنید.\nمثال: `52000`",
                    parse_mode=ParseMode.MARKDOWN
                )
    
    @staticmethod
    async def toggle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle payment method on/off"""
        query = update.callback_query
        await query.answer()
        
        method = query.data.replace('toggle_', '')
        
        # This would require updating config at runtime
        # For now, show instruction to admin
        text = f"""
⚙️ **تغییر وضعیت {method}**

برای تغییر وضعیت این روش پرداخت، لطفا فایل `.env` را ویرایش کنید:

```
{method.upper()}_ENABLED=true/false
```

سپس ربات را مجدداً راه‌اندازی کنید.
"""
        
        keyboard = [
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_payment_settings")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

# Admin callback handlers mapping
ADMIN_CALLBACKS = {
    'admin_panel': AdminHandlers.admin_panel,
    'admin_cards': AdminHandlers.manage_cards,
    'admin_wallets': AdminHandlers.manage_wallets,
    'admin_payment_settings': AdminHandlers.payment_settings,
    'admin_dollar_price': AdminHandlers.set_dollar_price,
    'admin_verify_payments': AdminHandlers.verify_payments,
    'toggle_aqay': AdminHandlers.toggle_payment_method,
    'toggle_card_to_card': AdminHandlers.toggle_payment_method,
    'toggle_crypto': AdminHandlers.toggle_payment_method,
}

# Dynamic handlers for approve/reject payments
def get_admin_callback_handler(callback_data: str):
    """Get appropriate admin callback handler"""
    if callback_data in ADMIN_CALLBACKS:
        return ADMIN_CALLBACKS[callback_data]
    elif callback_data.startswith('approve_payment_'):
        return AdminHandlers.approve_payment
    elif callback_data.startswith('reject_payment_'):
        return AdminHandlers.reject_payment
    else:
        return None