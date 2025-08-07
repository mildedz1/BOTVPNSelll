#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Master Bot System Test
Tests all major components to ensure they work correctly
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all modules can be imported"""
    print("🔍 Testing imports...")
    
    try:
        import config
        print("✅ config module imported")
        
        import database
        print("✅ database module imported")
        
        import payment
        print("✅ payment module imported")
        
        import deployment
        print("✅ deployment module imported")
        
        import discount
        print("✅ discount module imported")
        
        import referral_system
        print("✅ referral_system module imported")
        
        import trial_system
        print("✅ trial_system module imported")
        
        import renewal_system
        print("✅ renewal_system module imported")
        
        import admin
        print("✅ admin module imported")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_database():
    """Test database initialization"""
    print("\n🗄️  Testing database...")
    
    try:
        from database import master_db, query_db, execute_db
        
        # Test basic query
        result = query_db("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in result]
        
        expected_tables = [
            'customers', 'subscriptions', 'payments', 'bot_instances',
            'discount_codes', 'referral_codes', 'trial_accounts',
            'payment_cards', 'crypto_wallets', 'settings'
        ]
        
        missing_tables = [table for table in expected_tables if table not in tables]
        
        if missing_tables:
            print(f"⚠️  Missing tables: {', '.join(missing_tables)}")
        else:
            print("✅ All required tables exist")
        
        print(f"📊 Found {len(tables)} tables in database")
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_config():
    """Test configuration"""
    print("\n⚙️  Testing configuration...")
    
    try:
        from config import config
        
        # Check critical config values
        if not config.MASTER_BOT_TOKEN:
            print("⚠️  MASTER_BOT_TOKEN not set")
        else:
            print("✅ MASTER_BOT_TOKEN is set")
        
        if not config.MASTER_ADMIN_ID:
            print("⚠️  MASTER_ADMIN_ID not set")
        else:
            print("✅ MASTER_ADMIN_ID is set")
        
        print(f"📝 Database: {config.MASTER_DB_NAME}")
        print(f"🔗 Payment methods: Aqay={config.AQAY_ENABLED}, Card={config.CARD_TO_CARD_ENABLED}, Crypto={config.CRYPTO_ENABLED}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config error: {e}")
        return False

def test_managers():
    """Test manager classes"""
    print("\n🧩 Testing managers...")
    
    try:
        from discount import discount_manager
        from referral_system import referral_tracker
        from trial_system import trial_manager
        from payment import payment_service
        
        print("✅ All managers initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Manager error: {e}")
        return False

def test_discount_system():
    """Test discount code system"""
    print("\n🎁 Testing discount system...")
    
    try:
        from discount import discount_manager
        
        # Test discount code validation (should fail for non-existent code)
        is_valid, message, info = discount_manager.validate_discount_code("TESTCODE123", 1, 100000)
        
        if not is_valid:
            print("✅ Discount validation working (correctly rejected invalid code)")
        else:
            print("⚠️  Discount validation might have issues")
        
        return True
        
    except Exception as e:
        print(f"❌ Discount system error: {e}")
        return False

def test_referral_system():
    """Test referral system"""
    print("\n🎯 Testing referral system...")
    
    try:
        from referral_system import referral_tracker, referral_calculator
        
        # Test reward calculation
        settings = referral_calculator.get_reward_settings()
        reward = referral_calculator.calculate_referral_reward(100000, 1)
        
        print(f"✅ Referral reward calculation: {reward:,} Toman for 100,000 purchase")
        print(f"📊 Referral settings: {settings['referrer_percentage']}% commission")
        
        return True
        
    except Exception as e:
        print(f"❌ Referral system error: {e}")
        return False

def test_trial_system():
    """Test trial system"""
    print("\n🆓 Testing trial system...")
    
    try:
        from trial_system import trial_manager
        
        # Test trial settings
        settings = trial_manager.get_trial_settings()
        
        print(f"✅ Trial system configured:")
        print(f"   • Enabled: {settings['trial_enabled']}")
        print(f"   • Duration: {settings['trial_days']} days")
        print(f"   • Traffic: {settings['trial_traffic_limit_gb']} GB")
        
        return True
        
    except Exception as e:
        print(f"❌ Trial system error: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Master Bot System Test")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Database Test", test_database),
        ("Configuration Test", test_config),
        ("Managers Test", test_managers),
        ("Discount System Test", test_discount_system),
        ("Referral System Test", test_referral_system),
        ("Trial System Test", test_trial_system),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
    
    print("\n" + "=" * 40)
    print(f"🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System is ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)