# -*- coding: utf-8 -*-
"""
Master Bot - VPN Bot Deployment Service
Manages customer subscriptions and deploys VPN bots automatically
"""

import asyncio
import logging
from datetime import datetime, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# Import our modules
from config import config, States
from database import customer_repo, subscription_repo, query_db, execute_db
from deployment import deployment_service
from payment import payment_service
from admin import AdminHandlers, get_admin_callback_handler

# Setup logging
logger = logging.getLogger(__name__)

class MasterBotHandlers:
    """Main handlers for Master Bot"""
    
    @staticmethod
    async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /start command"""
        user = update.effective_user
        
        # Register customer if not exists
        customer = customer_repo.get_customer(user.id)
        if not customer:
            customer_id = customer_repo.create_customer(
                user_id=user.id,
                first_name=user.first_name,
                username=user.username
            )
            if customer_id:
                logger.info(f"Registered new customer: {user.id}")
        
        # Get welcome message from settings
        welcome_msg = query_db("SELECT value FROM settings WHERE key = 'welcome_message'", one=True)
        welcome_text = welcome_msg['value'] if welcome_msg else "🎉 به Master Bot خوش آمدید!"
        
        keyboard = [
            [InlineKeyboardButton("🚀 خرید ربات VPN", callback_data="buy_bot")],
            [InlineKeyboardButton("📦 رباتهای من", callback_data="my_bots")],
            [InlineKeyboardButton("💰 قیمت ها", callback_data="pricing")],
            [InlineKeyboardButton("🆘 پشتیبانی", callback_data="support")]
        ]
        
        # Add admin button for admin users
        if AdminHandlers.is_admin(user.id):
            keyboard.append([InlineKeyboardButton("🔧 پنل ادمین", callback_data="admin_panel")])
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.MAIN_MENU
    
    @staticmethod
    async def show_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show pricing plans"""
        query = update.callback_query
        await query.answer()
        
        monthly_price = config.MONTHLY_PRICE
        yearly_price = config.YEARLY_PRICE
        yearly_discount = int((1 - yearly_price / (monthly_price * 12)) * 100)
        
        # Get available payment methods
        payment_methods = payment_service.get_available_payment_methods()
        methods_text = ""
        
        for method_key, method_info in payment_methods.items():
            methods_text += f"{method_info['icon']} {method_info['name']}\n"
        
        pricing_text = f"""
💰 **قیمت گذاری سرویس**

🗓 **پلن ماهانه**
• قیمت: {monthly_price:,} تومان
• مدت: 30 روز
• تمدید خودکار: خیر

📅 **پلن سالانه** 
• قیمت: {yearly_price:,} تومان
• مدت: 365 روز  
• تخفیف: {yearly_discount}%
• تمدید خودکار: خیر

💳 **روش‌های پرداخت:**
{methods_text}

✨ **ویژگی های شامل:**
• ربات اختصاصی VPN
• پنل مدیریت کامل
• پشتیبانی چندین پنل Marzban  
• سیستم پرداخت متنوع
• آپدیت های رایگان
• پشتیبانی 24/7

🎯 **مناسب برای:**
• فروشندگان VPN
• شرکت های ارائه دهنده
• کارآفرینان حوزه فناوری
"""
        
        keyboard = [
            [InlineKeyboardButton("🛒 خرید پلن ماهانه", callback_data="buy_monthly")],
            [InlineKeyboardButton("💎 خرید پلن سالانه", callback_data="buy_yearly")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            pricing_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    @staticmethod
    async def start_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start purchase process"""
        query = update.callback_query
        await query.answer()
        
        plan_type = "monthly" if query.data == "buy_monthly" else "yearly"
        price = config.MONTHLY_PRICE if plan_type == "monthly" else config.YEARLY_PRICE
        
        context.user_data['purchase_plan'] = plan_type
        context.user_data['purchase_price'] = price
        
        text = f"""
🤖 **راه اندازی ربات VPN شما**

شما در حال خرید پلن **{"ماهانه" if plan_type == "monthly" else "سالانه"}** هستید.
💰 مبلغ: **{price:,} تومان**

برای راه اندازی ربات، به اطلاعات زیر نیاز داریم:

🔑 **توکن ربات تلگرام**
لطفا توکن ربات خود را از @BotFather دریافت کرده و ارسال کنید.

مثال: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
"""
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.AWAIT_BOT_TOKEN
    
    @staticmethod
    async def receive_bot_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive bot token from user"""
        bot_token = update.message.text.strip()
        
        # Basic validation
        if not bot_token or ':' not in bot_token:
            await update.message.reply_text(
                "❌ توکن نامعتبر است. لطفا توکن صحیح را ارسال کنید.\n"
                "مثال: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`",
                parse_mode=ParseMode.MARKDOWN
            )
            return States.AWAIT_BOT_TOKEN
        
        # Test bot token
        try:
            test_app = Application.builder().token(bot_token).build()
            bot_info = await test_app.bot.get_me()
            await test_app.shutdown()
            
            context.user_data['bot_token'] = bot_token
            context.user_data['bot_username'] = bot_info.username
            
            text = f"""
✅ توکن ربات تایید شد!
🤖 نام ربات: @{bot_info.username}

حالا آیدی عددی ادمین ربات را ارسال کنید.
این آیدی برای دسترسی به پنل مدیریت ربات استفاده می‌شود.

💡 برای دریافت آیدی عددی خود، به ربات @userinfobot پیام دهید.
"""
            
            await update.message.reply_text(text)
            return States.AWAIT_ADMIN_ID
            
        except Exception as e:
            logger.error(f"Bot token validation failed: {e}")
            await update.message.reply_text(
                "❌ توکن ربات نامعتبر است یا ربات غیرفعال می‌باشد.\n"
                "لطفا توکن صحیح را ارسال کنید."
            )
            return States.AWAIT_BOT_TOKEN
    
    @staticmethod
    async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive admin ID from user"""
        try:
            admin_id = int(update.message.text.strip())
            context.user_data['admin_id'] = admin_id
            
            text = """
✅ آیدی ادمین دریافت شد!

🔗 **اطلاعات کانال (اختیاری)**
اگر می‌خواهید کاربران برای استفاده از ربات باید در کانال شما عضو باشند، لطفا:

1️⃣ نام کاربری کانال (مثال: @mychannel)
2️⃣ آیدی عددی کانال (مثال: -1001234567890)

را با فرمت زیر ارسال کنید:
`@mychannel,-1001234567890`

یا اگر نمی‌خواهید از این قابلیت استفاده کنید، کلمه **رد** را ارسال کنید.
"""
            
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            return States.AWAIT_CHANNEL_INFO
            
        except ValueError:
            await update.message.reply_text(
                "❌ آیدی عددی نامعتبر است. لطفا فقط عدد ارسال کنید.\n"
                "مثال: `123456789`",
                parse_mode=ParseMode.MARKDOWN
            )
            return States.AWAIT_ADMIN_ID
    
    @staticmethod
    async def receive_channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive channel information"""
        channel_input = update.message.text.strip()
        
        if channel_input.lower() in ['رد', 'skip', 'no']:
            context.user_data['channel_username'] = None
            context.user_data['channel_id'] = None
        else:
            try:
                if ',' in channel_input:
                    username, channel_id = channel_input.split(',')
                    context.user_data['channel_username'] = username.strip()
                    context.user_data['channel_id'] = int(channel_id.strip())
                else:
                    await update.message.reply_text(
                        "❌ فرمت نامعتبر است. لطفا با فرمت `@channel,-1001234567890` ارسال کنید یا کلمه **رد** را بنویسید.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return States.AWAIT_CHANNEL_INFO
            except ValueError:
                await update.message.reply_text(
                    "❌ آیدی کانال نامعتبر است. لطفا عدد صحیح ارسال کنید."
                )
                return States.AWAIT_CHANNEL_INFO
        
        # Show summary and payment
        return await MasterBotHandlers.show_payment_summary(update, context)
    
    @staticmethod
    async def show_payment_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show payment summary and method selection"""
        plan_type = context.user_data.get('purchase_plan')
        price = context.user_data.get('purchase_price')
        bot_username = context.user_data.get('bot_username')
        
        channel_info = ""
        if context.user_data.get('channel_username'):
            channel_info = f"\n🔗 **کانال اجباری:** {context.user_data['channel_username']}"
        
        summary_text = f"""
📋 **خلاصه سفارش**

🤖 **ربات:** @{bot_username}
📦 **پلن:** {"ماهانه" if plan_type == "monthly" else "سالانه"}
💰 **مبلغ:** {price:,} تومان{channel_info}

💳 **انتخاب روش پرداخت:**
"""
        
        # Get available payment methods
        payment_methods = payment_service.get_available_payment_methods()
        keyboard = []
        
        for method_key, method_info in payment_methods.items():
            instant_text = " (فوری)" if method_info['instant'] else " (دستی)"
            keyboard.append([
                InlineKeyboardButton(
                    f"{method_info['icon']} {method_info['name']}{instant_text}",
                    callback_data=f"pay_with_{method_key}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")])
        
        await update.message.reply_text(
            summary_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.AWAIT_PAYMENT
    
    @staticmethod
    async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process payment with selected method"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_purchase":
            context.user_data.clear()
            await query.edit_message_text(
                "❌ خرید لغو شد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")
                ]])
            )
            return States.MAIN_MENU
        
        # Extract payment method from callback data
        if query.data.startswith("pay_with_"):
            payment_method = query.data.replace("pay_with_", "")
            context.user_data['payment_method'] = payment_method
        else:
            payment_method = context.user_data.get('payment_method', 'aqay')
        
        user = update.effective_user
        customer = customer_repo.get_customer(user.id)
        
        if not customer:
            await query.edit_message_text("❌ خطا در شناسایی کاربر.")
            return ConversationHandler.END
        
        # Create payment
        payment_data = {
            'customer_id': customer['id'],
            'amount': context.user_data['purchase_price'],
            'method': payment_method,
            'description': f"خرید ربات VPN - پلن {context.user_data['purchase_plan']}"
        }
        
        payment_url, transaction_id, payment_info = await payment_service.create_payment(payment_data)
        
        if payment_method == 'aqay' and payment_url:
            # Aqay Payment - Online gateway
            context.user_data['payment_transaction_id'] = transaction_id
            
            keyboard = [
                [InlineKeyboardButton("💳 پرداخت", url=payment_url)],
                [InlineKeyboardButton("✅ پرداخت کردم", callback_data="verify_payment")],
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
            ]
            
            await query.edit_message_text(
                "🌐 **درگاه آقای پرداخت**\n\n"
                "روی دکمه پرداخت کلیک کنید و پس از پرداخت موفق، دکمه 'پرداخت کردم' را بزنید.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return States.AWAIT_PAYMENT
            
        elif payment_method == 'card_to_card' and payment_info:
            # Card to Card Payment
            context.user_data['payment_transaction_id'] = transaction_id
            
            card_text = f"""
💳 **پرداخت کارت به کارت**

💰 **مبلغ:** {payment_info['amount']:,} تومان
🔢 **کد پرداخت:** {payment_info['payment_code']}

💳 **اطلاعات کارت:**
**شماره کارت:** `{payment_info['card_number']}`
**نام صاحب کارت:** {payment_info['card_name']}

📝 **راهنما:**
1️⃣ مبلغ {payment_info['amount']:,} تومان را به کارت بالا واریز کنید
2️⃣ کد پیگیری تراکنش را یادداشت کنید  
3️⃣ روی دکمه "✅ واریز کردم" کلیک کنید

⚠️ **توجه:** پرداخت شما پس از بررسی ادمین تایید خواهد شد.
"""
            
            if payment_info.get('instructions'):
                card_text += f"\n📋 **توضیحات:** {payment_info['instructions']}"
            
            keyboard = [
                [InlineKeyboardButton("✅ واریز کردم", callback_data="upload_screenshot")],
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
            ]
            
            await query.edit_message_text(
                card_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return States.AWAIT_PAYMENT
            
        elif payment_method == 'crypto' and payment_info:
            # Crypto Payment
            context.user_data['payment_transaction_id'] = transaction_id
            
            crypto_text = f"""
🪙 **پرداخت با رمز ارز**

💰 **مبلغ:** {payment_info['toman_amount']:,} تومان
💵 **قیمت دلار:** {payment_info['dollar_price']:,} تومان
🔢 **کد پرداخت:** {payment_info['payment_code']}

🪙 **اطلاعات کیف پول:**
**آدرس:** `{payment_info['wallet_address']}`
**نوع ارز:** {payment_info['crypto_type']}
**مقدار:** {payment_info['crypto_amount']} {payment_info['crypto_type']}
"""
            
            if payment_info.get('network'):
                crypto_text += f"**شبکه:** {payment_info['network']}\n"
            
            crypto_text += f"""
📝 **راهنما:**
1️⃣ مقدار {payment_info['crypto_amount']} {payment_info['crypto_type']} را به آدرس بالا ارسال کنید
2️⃣ Hash تراکنش را یادداشت کنید
3️⃣ روی دکمه "✅ ارسال کردم" کلیک کنید

⚠️ **توجه:** پرداخت شما پس از بررسی ادمین تایید خواهد شد.
"""
            
            if payment_info.get('instructions'):
                crypto_text += f"\n📋 **توضیحات:** {payment_info['instructions']}"
            
            keyboard = [
                [InlineKeyboardButton("✅ ارسال کردم", callback_data="upload_screenshot")],
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
            ]
            
            await query.edit_message_text(
                crypto_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return States.AWAIT_PAYMENT
            
        else:
            await query.edit_message_text(
                "❌ خطا در ایجاد پرداخت. لطفا بعداً تلاش کنید یا روش پرداخت دیگری انتخاب کنید."
            )
            return ConversationHandler.END
    
    @staticmethod
    async def request_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Request transaction screenshot from user"""
        query = update.callback_query
        await query.answer()
        
        payment_method = context.user_data.get('payment_method')
        
        if payment_method == 'card_to_card':
            screenshot_text = """
📸 **ارسال رسید تراکنش**

لطفا اسکرین‌شات رسید واریز خود را ارسال کنید:

📝 **راهنما:**
• عکس باید واضح و خوانا باشد
• تمام اطلاعات تراکنش باید مشخص باشه
• مبلغ و تاریخ/زمان واریز باید دیده بشه
• می‌توانید توضیحات اضافی هم بنویسید

⏰ **زمان تایید:** کمتر از 30 دقیقه
"""
        else:  # crypto
            screenshot_text = """
📸 **ارسال رسید تراکنش**

لطفا اسکرین‌شات تراکنش رمز ارز خود را ارسال کنید:

📝 **راهنما:**
• عکس باید واضح و خوانا باشد
• Hash تراکنش باید مشخص باشه
• مقدار و آدرس گیرنده باید دیده بشه
• وضعیت تایید شبکه نمایش داده شده باشه
• می‌توانید Hash تراکنش را هم بنویسید

⏰ **زمان تایید:** کمتر از 30 دقیقه
"""
        
        keyboard = [
            [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
        ]
        
        await query.edit_message_text(
            screenshot_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.AWAIT_TRANSACTION_SCREENSHOT
    
    @staticmethod
    async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive and process transaction screenshot"""
        user = update.effective_user
        transaction_id = context.user_data.get('payment_transaction_id')
        payment_method = context.user_data.get('payment_method')
        
        if not transaction_id:
            await update.message.reply_text("❌ خطا در شناسایی پرداخت.")
            return ConversationHandler.END
        
        screenshot_file_id = None
        screenshot_caption = ""
        
        # Get screenshot file_id
        if update.message.photo:
            # Get the highest resolution photo
            screenshot_file_id = update.message.photo[-1].file_id
            screenshot_caption = update.message.caption or ""
        elif update.message.document:
            # Handle document (image files sent as document)
            if update.message.document.mime_type and update.message.document.mime_type.startswith('image/'):
                screenshot_file_id = update.message.document.file_id
                screenshot_caption = update.message.caption or ""
            else:
                await update.message.reply_text(
                    "❌ لطفا فقط عکس ارسال کنید.\n"
                    "فرمت‌های مجاز: JPG, PNG"
                )
                return States.AWAIT_TRANSACTION_SCREENSHOT
        else:
            await update.message.reply_text(
                "❌ لطفا اسکرین‌شات تراکنش خود را ارسال کنید.\n"
                "می‌توانید عکس را مستقیم ارسال کنید یا به عنوان فایل."
            )
            return States.AWAIT_TRANSACTION_SCREENSHOT
        
        # Update payment record with screenshot info
        execute_db("""
            UPDATE payments 
            SET screenshot_file_id = ?, screenshot_caption = ?
            WHERE transaction_id = ?
        """, (screenshot_file_id, screenshot_caption, transaction_id))
        
        # Send confirmation to user
        await update.message.reply_text(
            f"""
✅ **رسید تراکنش دریافت شد!**

🔢 **کد پرداخت:** {transaction_id}
📸 **رسید:** ✅ دریافت شد
⏳ **وضعیت:** در انتظار تایید ادمین

📝 **اطلاعات شما ثبت شده و پس از بررسی رسید توسط ادمین، پرداخت تایید و ربات شما راه‌اندازی خواهد شد.**

⏰ **زمان تایید:** معمولاً کمتر از 30 دقیقه
🔔 **اطلاع‌رسانی:** پیام تایید به شما ارسال خواهد شد

💬 **پشتیبانی:** {query_db("SELECT value FROM settings WHERE key = 'support_contact'", one=True)['value'] if query_db("SELECT value FROM settings WHERE key = 'support_contact'", one=True) else '@YourSupportBot'}
            """,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send notification to admin with screenshot
        try:
            payment_method_text = "💳 کارت به کارت" if payment_method == 'card_to_card' else "🪙 رمز ارز"
            
            admin_text = f"""
🔔 **پرداخت جدید با رسید**

💳 **روش:** {payment_method_text}
🔢 **کد:** {transaction_id}
💰 **مبلغ:** {context.user_data.get('purchase_price', 0):,} تومان
👤 **مشتری:** {user.first_name} (@{user.username if user.username else 'بدون نام کاربری'})
📱 **آیدی:** {user.id}

📸 **رسید تراکنش در پیام بعدی ارسال می‌شود**

برای تایید/رد: /admin
            """
            
            await context.bot.send_message(
                chat_id=config.MASTER_ADMIN_ID,
                text=admin_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send the screenshot to admin
            if screenshot_file_id:
                caption = f"""
📸 **رسید پرداخت {transaction_id}**

👤 **مشتری:** {user.first_name}
💰 **مبلغ:** {context.user_data.get('purchase_price', 0):,} تومان

📝 **توضیحات مشتری:**
{screenshot_caption if screenshot_caption else 'بدون توضیحات'}

✅ **تایید:** /admin → تایید پرداخت‌ها
                """
                
                await context.bot.send_photo(
                    chat_id=config.MASTER_ADMIN_ID,
                    photo=screenshot_file_id,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Failed to send admin notification with screenshot: {e}")
        
        # Clear user data
        context.user_data.clear()
        return States.MAIN_MENU
    
    @staticmethod
    async def verify_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify payment and deploy bot"""
        query = update.callback_query
        await query.answer()
        
        transaction_id = context.user_data.get('payment_transaction_id')
        payment_method = context.user_data.get('payment_method', 'aqay')
        
        if not transaction_id:
            await query.edit_message_text("❌ خطا در شناسایی پرداخت.")
            return ConversationHandler.END
        
        # Verify payment
        verification_result = await payment_service.verify_payment(transaction_id, payment_method)
        
        if verification_result['status'] == 'success':
            await query.edit_message_text(
                "✅ پرداخت تایید شد!\n⏳ در حال راه‌اندازی ربات شما..."
            )
            
            # Deploy bot
            success = await MasterBotHandlers.deploy_customer_bot(update, context)
            
            if success:
                context.user_data.clear()
                return States.MAIN_MENU
            else:
                await query.edit_message_text(
                    "❌ خطا در راه‌اندازی ربات. لطفا با پشتیبانی تماس بگیرید."
                )
                return ConversationHandler.END
                
        elif verification_result['status'] == 'pending':
            # Manual payment methods (card-to-card, crypto)
            await query.edit_message_text(
                f"""
✅ **درخواست پرداخت ثبت شد!**

🔢 **کد پرداخت:** {transaction_id}
⏳ **وضعیت:** در انتظار تایید ادمین

📝 **اطلاعات شما ثبت شده و پس از تایید پرداخت توسط ادمین، ربات شما خودکار راه‌اندازی خواهد شد.**

⏰ **زمان تایید:** معمولاً کمتر از 30 دقیقه
🔔 **اطلاع‌رسانی:** پیام تایید به شما ارسال خواهد شد

💬 **پشتیبانی:** {query_db("SELECT value FROM settings WHERE key = 'support_contact'", one=True)['value'] if query_db("SELECT value FROM settings WHERE key = 'support_contact'", one=True) else '@YourSupportBot'}
                """,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send notification to admin
            try:
                await context.bot.send_message(
                    chat_id=config.MASTER_ADMIN_ID,
                    text=f"""
🔔 **پرداخت جدید در انتظار تایید**

💳 **روش:** {'کارت به کارت' if payment_method == 'card_to_card' else 'رمز ارز'}
🔢 **کد:** {transaction_id}
💰 **مبلغ:** {context.user_data.get('purchase_price', 0):,} تومان
👤 **مشتری:** {update.effective_user.first_name}

برای تایید به پنل ادمین مراجعه کنید: /admin
                    """,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
            
            context.user_data.clear()
            return States.MAIN_MENU
            
        else:
            await query.edit_message_text(
                f"❌ پرداخت تایید نشد: {verification_result.get('message', 'خطای نامشخص')}\n\n"
                "لطفا مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید."
            )
            return States.AWAIT_PAYMENT
    
    @staticmethod
    async def deploy_customer_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Deploy VPN bot for customer"""
        try:
            user = update.effective_user
            customer = customer_repo.get_customer(user.id)
            
            # Create subscription
            subscription_id = subscription_repo.create_subscription(
                customer_id=customer['id'],
                bot_token=context.user_data['bot_token'],
                admin_id=context.user_data['admin_id'],
                plan_type=context.user_data['purchase_plan'],
                price=context.user_data['purchase_price'],
                channel_username=context.user_data.get('channel_username'),
                channel_id=context.user_data.get('channel_id')
            )
            
            if not subscription_id:
                return False
            
            # Prepare deployment data
            deployment_data = {
                'customer_id': customer['id'],
                'subscription_id': subscription_id,
                'bot_token': context.user_data['bot_token'],
                'admin_id': context.user_data['admin_id'],
                'channel_username': context.user_data.get('channel_username'),
                'channel_id': context.user_data.get('channel_id')
            }
            
            # Deploy bot
            success, message, deployment_info = deployment_service.deploy_bot(deployment_data)
            
            if success:
                # Update subscription with deployment info
                subscription_repo.update_subscription(
                    subscription_id,
                    container_id=deployment_info['container_id'],
                    bot_url=deployment_info['bot_url']
                )
                
                # Send success message
                success_text = f"""
🎉 **ربات شما با موفقیت راه‌اندازی شد!**

🤖 **ربات:** @{context.user_data['bot_username']}
🔗 **لینک:** {deployment_info['bot_url']}
📦 **وضعیت:** فعال

✅ ربات شما آماده استفاده است!
می‌توانید از منوی "رباتهای من" وضعیت ربات را مشاهده کنید.

🆘 **پشتیبانی:** {query_db("SELECT value FROM settings WHERE key = 'support_contact'", one=True)['value']}
"""
                
                keyboard = [[InlineKeyboardButton("📦 مشاهده رباتهای من", callback_data="my_bots")]]
                
                await update.callback_query.edit_message_text(
                    success_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                
                return True
            else:
                logger.error(f"Bot deployment failed: {message}")
                return False
                
        except Exception as e:
            logger.error(f"Error in deploy_customer_bot: {e}")
            return False
    
    @staticmethod
    async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's bots"""
        query = update.callback_query
        await query.answer()
        
        user = update.effective_user
        customer = customer_repo.get_customer(user.id)
        
        if not customer:
            await query.edit_message_text("❌ کاربر یافت نشد.")
            return
        
        subscriptions = subscription_repo.get_customer_subscriptions(customer['id'])
        
        if not subscriptions:
            await query.edit_message_text(
                "📭 شما هنوز هیچ ربات VPN ندارید.\n\n"
                "برای خرید ربات جدید از دکمه زیر استفاده کنید.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛒 خرید ربات جدید", callback_data="buy_bot"),
                    InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")
                ]])
            )
            return
        
        text = "🤖 **رباتهای شما:**\n\n"
        keyboard = []
        
        for sub in subscriptions:
            status_emoji = "✅" if sub['status'] == 'active' else "❌"
            plan_text = "ماهانه" if sub['plan_type'] == 'monthly' else "سالانه"
            
            # Get bot username from token
            try:
                bot_id = sub['bot_token'].split(':')[0]
                text += f"{status_emoji} **ربات #{bot_id}**\n"
                text += f"   📦 پلن: {plan_text}\n"
                text += f"   📅 انقضا: {sub['end_date'][:10]}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"مدیریت ربات #{bot_id}", callback_data=f"manage_bot_{sub['id']}")
                ])
            except:
                pass
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

def create_master_bot_application() -> Application:
    """Create and configure the master bot application"""
    application = Application.builder().token(config.MASTER_BOT_TOKEN).build()
    
    # Conversation handler for purchase flow
    purchase_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(MasterBotHandlers.start_purchase, pattern=r'^buy_(monthly|yearly)$')
        ],
        states={
            States.AWAIT_BOT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, MasterBotHandlers.receive_bot_token)],
            States.AWAIT_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, MasterBotHandlers.receive_admin_id)],
            States.AWAIT_CHANNEL_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, MasterBotHandlers.receive_channel_info)],
            States.AWAIT_PAYMENT: [
                CallbackQueryHandler(MasterBotHandlers.process_payment, pattern=r'^pay_with_'),
                CallbackQueryHandler(MasterBotHandlers.verify_payment, pattern=r'^verify_payment$'),
                CallbackQueryHandler(MasterBotHandlers.request_screenshot, pattern=r'^upload_screenshot$'),
                CallbackQueryHandler(MasterBotHandlers.process_payment, pattern=r'^cancel_purchase$')
            ],
            States.ADMIN_SETTINGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, AdminHandlers.handle_admin_input)
            ],
            States.AWAIT_TRANSACTION_SCREENSHOT: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, MasterBotHandlers.receive_screenshot),
                CallbackQueryHandler(MasterBotHandlers.process_payment, pattern=r'^cancel_purchase$')
            ]
        },
        fallbacks=[CommandHandler('start', MasterBotHandlers.start_command)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', MasterBotHandlers.start_command))
    application.add_handler(CommandHandler('admin', AdminHandlers.admin_panel))
    application.add_handler(purchase_conv)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(MasterBotHandlers.show_pricing, pattern=r'^pricing$'))
    application.add_handler(CallbackQueryHandler(MasterBotHandlers.my_bots, pattern=r'^my_bots$'))
    
    # Admin callback handlers
    def admin_callback_router(update, context):
        """Route admin callbacks to appropriate handlers"""
        callback_data = update.callback_query.data
        handler = get_admin_callback_handler(callback_data)
        if handler:
            return handler(update, context)
        return None
    
    # Add admin callback handlers
    application.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^admin_'))
    application.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^toggle_'))
    application.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^approve_payment_'))
    application.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^reject_payment_'))
    application.add_handler(CallbackQueryHandler(admin_callback_router, pattern=r'^view_screenshot_'))
    
    return application

def main():
    """Main function to run the master bot"""
    try:
        logger.info("Starting Master Bot...")
        logger.info(f"Admin ID: {config.MASTER_ADMIN_ID}")
        
        application = create_master_bot_application()
        
        logger.info("Master Bot is running... Press Ctrl+C to stop.")
        application.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        logger.info("Master Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        logger.info("Master Bot shutdown complete")

if __name__ == "__main__":
    main()