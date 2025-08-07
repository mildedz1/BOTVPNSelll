#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup script for Master Bot payment methods
Adds sample payment cards and crypto wallets to database
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import execute_db, query_db

def setup_payment_cards():
    """Add sample payment cards"""
    print("🔧 Setting up payment cards...")
    
    sample_cards = [
        {
            'card_number': '6037-9918-1234-5678',
            'card_name': 'احمد محمدی',
            'bank_name': 'بانک کشاورزی',
            'instructions': 'لطفا پس از واریز، کد پیگیری را یادداشت کنید',
            'priority': 1
        },
        {
            'card_number': '5022-2910-8765-4321',
            'card_name': 'فاطمه احمدی',
            'bank_name': 'بانک ملت',
            'instructions': 'واریز فقط در ساعات اداری امکان‌پذیر است',
            'priority': 2
        },
        {
            'card_number': '6274-1291-9876-5432',
            'card_name': 'علی رضایی',
            'bank_name': 'بانک صادرات',
            'instructions': 'برای تسریع در تایید، از نام خودتان واریز کنید',
            'priority': 3
        }
    ]
    
    for card in sample_cards:
        # Check if card already exists
        existing = query_db("SELECT id FROM payment_cards WHERE card_number = ?", (card['card_number'],), one=True)
        
        if not existing:
            execute_db("""
                INSERT INTO payment_cards (card_number, card_name, bank_name, instructions, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (card['card_number'], card['card_name'], card['bank_name'], 
                  card['instructions'], card['priority']))
            print(f"✅ Added card: {card['card_number']} - {card['card_name']}")
        else:
            print(f"⚠️  Card already exists: {card['card_number']}")
    
    print(f"✅ Payment cards setup completed!\n")

def setup_crypto_wallets():
    """Add sample crypto wallets"""
    print("🔧 Setting up crypto wallets...")
    
    sample_wallets = [
        {
            'wallet_address': 'TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE',
            'crypto_type': 'USDT',
            'network': 'TRC20 (Tron)',
            'instructions': 'فقط از شبکه TRC20 استفاده کنید - هزینه کمتر',
            'priority': 1
        },
        {
            'wallet_address': '0x742d35Cc6634C0532925a3b8D4C7C8d8d8f8A8B1',
            'crypto_type': 'USDT',
            'network': 'ERC20 (Ethereum)',
            'instructions': 'توجه: هزینه تراکنش در این شبکه بالا است',
            'priority': 2
        },
        {
            'wallet_address': '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',
            'crypto_type': 'BTC',
            'network': 'Bitcoin',
            'instructions': 'حداقل 3 تایید شبکه منتظر بمانید',
            'priority': 3
        },
        {
            'wallet_address': '0x742d35Cc6634C0532925a3b8D4C7C8d8d8f8A8B2',
            'crypto_type': 'ETH',
            'network': 'Ethereum',
            'instructions': 'مقدار Gas Fee را در نظر بگیرید',
            'priority': 4
        },
        {
            'wallet_address': 'TPuDCYmF7KNWmywiNjkQDerp9LqJHnGCYL',
            'crypto_type': 'TRX',
            'network': 'Tron',
            'instructions': 'سریعترین و ارزان‌ترین روش پرداخت',
            'priority': 5
        }
    ]
    
    for wallet in sample_wallets:
        # Check if wallet already exists
        existing = query_db("SELECT id FROM crypto_wallets WHERE wallet_address = ?", (wallet['wallet_address'],), one=True)
        
        if not existing:
            execute_db("""
                INSERT INTO crypto_wallets (wallet_address, crypto_type, network, instructions, priority)
                VALUES (?, ?, ?, ?, ?)
            """, (wallet['wallet_address'], wallet['crypto_type'], wallet['network'], 
                  wallet['instructions'], wallet['priority']))
            print(f"✅ Added wallet: {wallet['crypto_type']} - {wallet['wallet_address'][:20]}...")
        else:
            print(f"⚠️  Wallet already exists: {wallet['wallet_address'][:20]}...")
    
    print(f"✅ Crypto wallets setup completed!\n")

def setup_default_settings():
    """Setup default system settings"""
    print("🔧 Setting up default settings...")
    
    default_settings = {
        'dollar_price': '52000',
        'welcome_message': '''🎉 به Master Bot خوش آمدید!

🤖 با این ربات می‌توانید ربات فروش VPN شخصی خود را راه‌اندازی کنید.

✨ ویژگی‌های سیستم:
• راه‌اندازی خودکار در 5 دقیقه
• پشتیبانی از چندین روش پرداخت
• پنل مدیریت اختصاصی
• پشتیبانی 24/7

🚀 برای شروع، روی "💰 قیمت ها" کلیک کنید.''',
        
        'payment_message': '💳 لطفا روش پرداخت مورد نظر خود را انتخاب کنید:',
        'success_message': '''✅ پرداخت شما با موفقیت انجام شد!

⏳ ربات شما در حال راه‌اندازی است...
🔔 اطلاعات دسترسی به زودی ارسال خواهد شد.''',
        
        'support_contact': '@MasterBotSupport',
        'maintenance_mode': 'false',
        'max_bots_per_customer': '5'
    }
    
    for key, value in default_settings.items():
        existing = query_db("SELECT id FROM settings WHERE key = ?", (key,), one=True)
        
        if not existing:
            execute_db("""
                INSERT INTO settings (key, value, description)
                VALUES (?, ?, ?)
            """, (key, value, f"Default setting for {key}"))
            print(f"✅ Added setting: {key}")
        else:
            print(f"⚠️  Setting already exists: {key}")
    
    print(f"✅ Default settings setup completed!\n")

def show_status():
    """Show current payment methods status"""
    print("📊 Current Payment Methods Status:")
    print("=" * 50)
    
    # Payment cards
    cards = query_db("SELECT * FROM payment_cards WHERE is_active = 1 ORDER BY priority")
    print(f"💳 Active Payment Cards: {len(cards)}")
    for card in cards:
        print(f"   • {card['card_name']} - {card['card_number']} ({card['bank_name']})")
    
    print()
    
    # Crypto wallets  
    wallets = query_db("SELECT * FROM crypto_wallets WHERE is_active = 1 ORDER BY priority")
    print(f"🪙 Active Crypto Wallets: {len(wallets)}")
    for wallet in wallets:
        print(f"   • {wallet['crypto_type']} - {wallet['wallet_address'][:25]}... ({wallet['network']})")
    
    print()
    
    # Settings
    dollar_price = query_db("SELECT value FROM settings WHERE key = 'dollar_price'", one=True)
    print(f"💵 Dollar Price: {dollar_price['value'] if dollar_price else 'Not set'} تومان")
    
    print("=" * 50)

def main():
    """Main setup function"""
    print("🚀 Master Bot Payment Methods Setup")
    print("=" * 50)
    
    try:
        # Setup payment methods
        setup_payment_cards()
        setup_crypto_wallets()
        setup_default_settings()
        
        print("🎉 Setup completed successfully!")
        print("\n📋 Summary:")
        show_status()
        
        print("\n💡 Next Steps:")
        print("1. Update .env file with your actual payment gateway credentials")
        print("2. Replace sample card numbers and wallets with your real ones")
        print("3. Configure dollar price via admin panel: /admin")
        print("4. Test payment methods before going live")
        print("\n✅ Your Master Bot is ready to accept payments!")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)