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

✨ **ویژگی های شامل:**
• ربات اختصاصی VPN
• پنل مدیریت کامل
• پشتیبانی چندین پنل Marzban  
• سیستم پرداخت آنلاین
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
        """Show payment summary"""
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

✅ همه چیز آماده است! برای پرداخت و راه‌اندازی ربات روی دکمه زیر کلیک کنید.

⚡ پس از پرداخت موفق، ربات شما ظرف 2-5 دقیقه راه‌اندازی خواهد شد.
"""
        
        keyboard = [
            [InlineKeyboardButton("💳 پرداخت و راه‌اندازی", callback_data="proceed_payment")],
            [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
        ]
        
        await update.message.reply_text(
            summary_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return States.AWAIT_PAYMENT
    
    @staticmethod
    async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Process payment"""
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
        
        user = update.effective_user
        customer = customer_repo.get_customer(user.id)
        
        if not customer:
            await query.edit_message_text("❌ خطا در شناسایی کاربر.")
            return ConversationHandler.END
        
        # Create payment
        payment_data = {
            'customer_id': customer['id'],
            'amount': context.user_data['purchase_price'],
            'description': f"خرید ربات VPN - پلن {context.user_data['purchase_plan']}"
        }
        
        payment_url, authority = await payment_service.create_payment(payment_data)
        
        if payment_url:
            # Store payment info in context
            context.user_data['payment_authority'] = authority
            
            keyboard = [
                [InlineKeyboardButton("💳 پرداخت", url=payment_url)],
                [InlineKeyboardButton("✅ پرداخت کردم", callback_data="verify_payment")],
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_purchase")]
            ]
            
            await query.edit_message_text(
                "💳 **پرداخت**\n\n"
                "روی دکمه پرداخت کلیک کنید و پس از پرداخت موفق، دکمه 'پرداخت کردم' را بزنید.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            
            return States.AWAIT_PAYMENT
        else:
            await query.edit_message_text(
                "❌ خطا در ایجاد لینک پرداخت. لطفا بعداً تلاش کنید."
            )
            return ConversationHandler.END
    
    @staticmethod
    async def verify_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Verify payment and deploy bot"""
        query = update.callback_query
        await query.answer()
        
        authority = context.user_data.get('payment_authority')
        if not authority:
            await query.edit_message_text("❌ خطا در شناسایی پرداخت.")
            return ConversationHandler.END
        
        # Verify payment
        verification_result = await payment_service.verify_payment(authority)
        
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
                CallbackQueryHandler(MasterBotHandlers.process_payment, pattern=r'^proceed_payment$'),
                CallbackQueryHandler(MasterBotHandlers.verify_payment, pattern=r'^verify_payment$'),
                CallbackQueryHandler(MasterBotHandlers.process_payment, pattern=r'^cancel_purchase$')
            ]
        },
        fallbacks=[CommandHandler('start', MasterBotHandlers.start_command)]
    )
    
    # Add handlers
    application.add_handler(CommandHandler('start', MasterBotHandlers.start_command))
    application.add_handler(purchase_conv)
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(MasterBotHandlers.show_pricing, pattern=r'^pricing$'))
    application.add_handler(CallbackQueryHandler(MasterBotHandlers.my_bots, pattern=r'^my_bots$'))
    
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