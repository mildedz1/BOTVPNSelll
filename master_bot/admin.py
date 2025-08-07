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
from discount import discount_manager, broadcast_manager, notes_manager

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
                InlineKeyboardButton("🎁 مدیریت کدهای تخفیف", callback_data="admin_discount_codes"),
                InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast")
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
                
                text += f"📅 **تاریخ:** {payment['created_at'][:16]}\n"
                
                # Show screenshot status
                if payment['screenshot_file_id']:
                    text += f"📸 **رسید:** ✅ دریافت شده\n"
                    if payment['screenshot_caption']:
                        text += f"📝 **توضیحات:** {payment['screenshot_caption'][:50]}{'...' if len(payment['screenshot_caption']) > 50 else ''}\n"
                else:
                    text += f"📸 **رسید:** ❌ ارسال نشده\n"
                
                text += "\n"
                
                # Add buttons for approve/reject and view screenshot
                buttons_row = [
                    InlineKeyboardButton(f"✅ تایید", callback_data=f"approve_payment_{payment['id']}"),
                    InlineKeyboardButton(f"❌ رد", callback_data=f"reject_payment_{payment['id']}")
                ]
                
                if payment['screenshot_file_id']:
                    buttons_row.append(
                        InlineKeyboardButton(f"📸 رسید", callback_data=f"view_screenshot_{payment['id']}")
                    )
                
                keyboard.append(buttons_row)
            
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
    async def view_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View payment screenshot"""
        query = update.callback_query
        await query.answer()
        
        payment_id = int(query.data.split('_')[-1])
        
        # Get payment with screenshot info
        payment = query_db("""
            SELECT p.*, c.first_name, c.username, c.user_id,
                   pc.card_number, pc.card_name,
                   cw.wallet_address, cw.crypto_type, p.crypto_amount,
                   p.screenshot_file_id, p.screenshot_caption
            FROM payments p
            LEFT JOIN customers c ON p.customer_id = c.id
            LEFT JOIN payment_cards pc ON p.card_id = pc.id
            LEFT JOIN crypto_wallets cw ON p.wallet_id = cw.id
            WHERE p.id = ?
        """, (payment_id,), one=True)
        
        if not payment:
            await query.edit_message_text("❌ پرداخت یافت نشد.")
            return
        
        if not payment['screenshot_file_id']:
            await query.edit_message_text("❌ رسید تراکنش ارسال نشده است.")
            return
        
        try:
            # Prepare payment details
            method_text = "💳 کارت به کارت" if payment['payment_method'] == 'card_to_card' else "🪙 رمز ارز"
            
            caption = f"""
📸 **رسید پرداخت {payment['transaction_id']}**

💳 **روش:** {method_text}
👤 **مشتری:** {payment['first_name']} (@{payment['username'] if payment['username'] else 'بدون نام کاربری'})
📱 **آیدی:** {payment['user_id']}
💰 **مبلغ:** {payment['amount']:,} تومان
📅 **تاریخ:** {payment['created_at'][:16]}

📝 **توضیحات مشتری:**
{payment['screenshot_caption'] if payment['screenshot_caption'] else 'بدون توضیحات'}

✅ **تایید:** دکمه تایید در زیر
❌ **رد:** دکمه رد در زیر
            """
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ تایید پرداخت", callback_data=f"approve_payment_{payment['id']}"),
                    InlineKeyboardButton("❌ رد پرداخت", callback_data=f"reject_payment_{payment['id']}")
                ],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_verify_payments")]
            ]
            
            # Send the screenshot with details
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=payment['screenshot_file_id'],
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Delete the original message
            await query.delete_message()
            
        except Exception as e:
            logger.error(f"Failed to show screenshot: {e}")
            await query.edit_message_text(
                f"❌ خطا در نمایش رسید.\n\nجزئیات پرداخت:\n"
                f"کد: {payment['transaction_id']}\n"
                f"مشتری: {payment['first_name']}\n"
                f"مبلغ: {payment['amount']:,} تومان",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data="admin_verify_payments")
                ]])
            )
    
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
    
    @staticmethod
    async def manage_discount_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manage discount codes"""
        query = update.callback_query
        await query.answer()
        
        discount_codes = discount_manager.get_discount_codes(active_only=False)
        
        text = "🎁 **مدیریت کدهای تخفیف**\n\n"
        keyboard = []
        
        if discount_codes:
            for code in discount_codes[:10]:  # Show max 10
                status_emoji = "✅" if code['is_active'] else "❌"
                usage_text = f"{code['used_count']}"
                if code['max_uses'] > 0:
                    usage_text += f"/{code['max_uses']}"
                
                discount_text = f"{code['discount_percent']}%" if code['discount_percent'] > 0 else f"{code['discount_amount']:,}T"
                
                text += f"{status_emoji} **{code['code']}**\n"
                text += f"   💸 تخفیف: {discount_text}\n"
                text += f"   📊 استفاده: {usage_text}\n"
                text += f"   🎯 برای: {code['valid_for']}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"ویرایش {code['code']}", callback_data=f"edit_discount_{code['id']}")
                ])
        else:
            text += "📭 هیچ کد تخفیفی تعریف نشده است.\n\n"
        
        keyboard.extend([
            [InlineKeyboardButton("➕ ایجاد کد تخفیف جدید", callback_data="create_discount_code")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Broadcast message menu"""
        query = update.callback_query
        await query.answer()
        
        # Get customer counts
        all_customers = len(broadcast_manager.get_all_customers())
        active_subs = len(broadcast_manager.get_customers_with_active_subscriptions())
        expired_subs = len(broadcast_manager.get_customers_with_expired_subscriptions())
        
        text = f"""
📢 **پیام همگانی**

👥 **آمار مخاطبان:**
• همه مشتریان: {all_customers:,} نفر
• اشتراک فعال: {active_subs:,} نفر  
• اشتراک منقضی: {expired_subs:,} نفر

لطفا گروه مخاطب مورد نظر را انتخاب کنید:
"""
        
        keyboard = [
            [InlineKeyboardButton(f"👥 همه مشتریان ({all_customers})", callback_data="broadcast_all")],
            [InlineKeyboardButton(f"✅ اشتراک فعال ({active_subs})", callback_data="broadcast_active")],
            [InlineKeyboardButton(f"⏰ اشتراک منقضی ({expired_subs})", callback_data="broadcast_expired")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
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
    'admin_discount_codes': AdminHandlers.manage_discount_codes,
    'admin_broadcast': AdminHandlers.broadcast_menu,
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
    elif callback_data.startswith('view_screenshot_'):
        return AdminHandlers.view_screenshot
    else:
        return None