# -*- coding: utf-8 -*-
"""
Referral System for Master Bot
Handles referral codes, rewards, and affiliate tracking
"""

import logging
import string
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from database import execute_db, query_db

logger = logging.getLogger(__name__)

class ReferralCodeGenerator:
    """Generates unique referral codes"""
    
    @staticmethod
    def generate_referral_code(user_id: int, length: int = 6) -> str:
        """Generate unique referral code for user"""
        
        # Use user_id + random chars for uniqueness
        base = f"REF{user_id}"
        random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        
        return f"{base[-3:]}{random_chars}"
    
    @staticmethod
    def create_referral_code(customer_id: int) -> Optional[str]:
        """Create referral code for customer"""
        
        try:
            # Check if customer already has a referral code
            existing = query_db("""
                SELECT referral_code FROM referral_codes 
                WHERE customer_id = ? AND is_active = 1
            """, (customer_id,), one=True)
            
            if existing:
                return existing['referral_code']
            
            # Generate new code
            max_attempts = 10
            for _ in range(max_attempts):
                code = ReferralCodeGenerator.generate_referral_code(customer_id)
                
                # Check if code is unique
                exists = query_db("""
                    SELECT id FROM referral_codes WHERE referral_code = ?
                """, (code,), one=True)
                
                if not exists:
                    # Create referral code
                    execute_db("""
                        INSERT INTO referral_codes (customer_id, referral_code, is_active)
                        VALUES (?, ?, 1)
                    """, (customer_id, code))
                    
                    logger.info(f"Created referral code {code} for customer {customer_id}")
                    return code
            
            logger.error(f"Failed to generate unique referral code for customer {customer_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error creating referral code: {e}")
            return None

class ReferralRewardCalculator:
    """Calculates referral rewards"""
    
    # Default reward settings
    DEFAULT_REFERRER_PERCENTAGE = 15  # 15% commission
    DEFAULT_REFEREE_DISCOUNT = 10     # 10% discount for new user
    
    @staticmethod
    def get_reward_settings() -> Dict:
        """Get current reward settings"""
        
        settings = query_db("""
            SELECT key, value FROM settings 
            WHERE key IN ('referrer_percentage', 'referee_discount_percentage', 'min_payout_amount')
        """)
        
        result = {
            'referrer_percentage': ReferralRewardCalculator.DEFAULT_REFERRER_PERCENTAGE,
            'referee_discount': ReferralRewardCalculator.DEFAULT_REFEREE_DISCOUNT,
            'min_payout_amount': 50000  # 50,000 Toman minimum
        }
        
        for setting in settings:
            if setting['key'] == 'referrer_percentage':
                result['referrer_percentage'] = int(setting['value'])
            elif setting['key'] == 'referee_discount_percentage':
                result['referee_discount'] = int(setting['value'])
            elif setting['key'] == 'min_payout_amount':
                result['min_payout_amount'] = int(setting['value'])
        
        return result
    
    @staticmethod
    def calculate_referral_reward(purchase_amount: int, referrer_id: int) -> int:
        """Calculate referral reward amount"""
        
        settings = ReferralRewardCalculator.get_reward_settings()
        reward_amount = int((purchase_amount * settings['referrer_percentage']) / 100)
        
        return reward_amount
    
    @staticmethod
    def calculate_referee_discount(purchase_amount: int) -> int:
        """Calculate discount for new referee"""
        
        settings = ReferralRewardCalculator.get_reward_settings()
        discount_amount = int((purchase_amount * settings['referee_discount']) / 100)
        
        return discount_amount

class ReferralWalletManager:
    """Manages referral wallet and payouts"""
    
    @staticmethod
    def get_wallet_balance(customer_id: int) -> int:
        """Get customer's referral wallet balance"""
        
        balance = query_db("""
            SELECT COALESCE(SUM(
                CASE 
                    WHEN transaction_type = 'credit' THEN amount
                    WHEN transaction_type = 'debit' THEN -amount
                    ELSE 0
                END
            ), 0) as balance
            FROM referral_wallet_transactions 
            WHERE customer_id = ?
        """, (customer_id,), one=True)
        
        return balance['balance'] if balance else 0
    
    @staticmethod
    def add_referral_reward(referrer_id: int, referee_id: int, amount: int, purchase_id: int) -> bool:
        """Add referral reward to wallet"""
        
        try:
            execute_db("""
                INSERT INTO referral_wallet_transactions 
                (customer_id, transaction_type, amount, description, related_customer_id, related_purchase_id)
                VALUES (?, 'credit', ?, ?, ?, ?)
            """, (
                referrer_id, 
                amount, 
                f"پاداش معرفی کاربر جدید - {amount:,} تومان",
                referee_id,
                purchase_id
            ))
            
            # Update referral statistics
            execute_db("""
                UPDATE referral_codes 
                SET total_referrals = total_referrals + 1,
                    total_earnings = total_earnings + ?
                WHERE customer_id = ?
            """, (amount, referrer_id))
            
            logger.info(f"Added referral reward {amount} to customer {referrer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding referral reward: {e}")
            return False
    
    @staticmethod
    def request_payout(customer_id: int, amount: int, bank_info: Dict) -> Optional[int]:
        """Request payout from referral wallet"""
        
        try:
            # Check balance
            current_balance = ReferralWalletManager.get_wallet_balance(customer_id)
            
            if current_balance < amount:
                return None
            
            # Check minimum payout amount
            settings = ReferralRewardCalculator.get_reward_settings()
            if amount < settings['min_payout_amount']:
                return None
            
            # Create payout request
            payout_id = execute_db("""
                INSERT INTO referral_payouts 
                (customer_id, amount, bank_account, bank_name, account_holder, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (
                customer_id,
                amount,
                bank_info.get('account_number'),
                bank_info.get('bank_name'),
                bank_info.get('account_holder')
            ))
            
            # Debit from wallet
            execute_db("""
                INSERT INTO referral_wallet_transactions 
                (customer_id, transaction_type, amount, description, related_payout_id)
                VALUES (?, 'debit', ?, ?, ?)
            """, (
                customer_id,
                amount,
                f"درخواست برداشت - {amount:,} تومان",
                payout_id
            ))
            
            logger.info(f"Created payout request {payout_id} for customer {customer_id}")
            return payout_id
            
        except Exception as e:
            logger.error(f"Error requesting payout: {e}")
            return None
    
    @staticmethod
    def get_payout_requests(customer_id: Optional[int] = None, status: str = None) -> List[Dict]:
        """Get payout requests"""
        
        query = """
            SELECT rp.*, c.first_name, c.username, c.user_id
            FROM referral_payouts rp
            JOIN customers c ON rp.customer_id = c.id
            WHERE 1=1
        """
        params = []
        
        if customer_id:
            query += " AND rp.customer_id = ?"
            params.append(customer_id)
        
        if status:
            query += " AND rp.status = ?"
            params.append(status)
        
        query += " ORDER BY rp.created_at DESC"
        
        return query_db(query, params)

class ReferralTracker:
    """Tracks referral usage and statistics"""
    
    @staticmethod
    def apply_referral_code(referee_id: int, referral_code: str) -> Tuple[bool, str, Optional[Dict]]:
        """Apply referral code for new customer"""
        
        try:
            # Get referral code info
            referral_info = query_db("""
                SELECT rc.*, c.first_name, c.username
                FROM referral_codes rc
                JOIN customers c ON rc.customer_id = c.id
                WHERE rc.referral_code = ? AND rc.is_active = 1
            """, (referral_code.upper(),), one=True)
            
            if not referral_info:
                return False, "کد معرف معتبر نیست", None
            
            # Check if user is trying to refer themselves
            if referral_info['customer_id'] == referee_id:
                return False, "نمی‌توانید از کد معرف خود استفاده کنید", None
            
            # Check if customer has already used a referral code
            existing_referral = query_db("""
                SELECT id FROM referral_usage 
                WHERE referee_id = ?
            """, (referee_id,), one=True)
            
            if existing_referral:
                return False, "شما قبلاً از کد معرف استفاده کرده‌اید", None
            
            # Record referral usage
            execute_db("""
                INSERT INTO referral_usage (referrer_id, referee_id, referral_code, status)
                VALUES (?, ?, ?, 'pending')
            """, (referral_info['customer_id'], referee_id, referral_code.upper()))
            
            return True, "کد معرف با موفقیت اعمال شد", referral_info
            
        except Exception as e:
            logger.error(f"Error applying referral code: {e}")
            return False, "خطا در اعمال کد معرف", None
    
    @staticmethod
    def complete_referral(referee_id: int, purchase_amount: int, purchase_id: int) -> bool:
        """Complete referral process after successful purchase"""
        
        try:
            # Get pending referral
            referral = query_db("""
                SELECT * FROM referral_usage 
                WHERE referee_id = ? AND status = 'pending'
            """, (referee_id,), one=True)
            
            if not referral:
                return False
            
            # Calculate rewards
            reward_amount = ReferralRewardCalculator.calculate_referral_reward(
                purchase_amount, referral['referrer_id']
            )
            
            # Add reward to referrer's wallet
            ReferralWalletManager.add_referral_reward(
                referral['referrer_id'], 
                referee_id, 
                reward_amount, 
                purchase_id
            )
            
            # Mark referral as completed
            execute_db("""
                UPDATE referral_usage 
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    reward_amount = ?, purchase_id = ?
                WHERE id = ?
            """, (reward_amount, purchase_id, referral['id']))
            
            logger.info(f"Completed referral for referee {referee_id}, reward {reward_amount}")
            return True
            
        except Exception as e:
            logger.error(f"Error completing referral: {e}")
            return False
    
    @staticmethod
    def get_referral_statistics(customer_id: int) -> Dict:
        """Get referral statistics for customer"""
        
        stats = query_db("""
            SELECT 
                COUNT(*) as total_referrals,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful_referrals,
                COALESCE(SUM(reward_amount), 0) as total_earned
            FROM referral_usage 
            WHERE referrer_id = ?
        """, (customer_id,), one=True)
        
        wallet_balance = ReferralWalletManager.get_wallet_balance(customer_id)
        
        return {
            'total_referrals': stats['total_referrals'] if stats else 0,
            'successful_referrals': stats['successful_referrals'] if stats else 0,
            'total_earned': stats['total_earned'] if stats else 0,
            'wallet_balance': wallet_balance,
            'pending_referrals': (stats['total_referrals'] - stats['successful_referrals']) if stats else 0
        }
    
    @staticmethod
    def get_top_referrers(limit: int = 10) -> List[Dict]:
        """Get top referrers leaderboard"""
        
        return query_db("""
            SELECT c.first_name, c.username, c.user_id,
                   rc.total_referrals, rc.total_earnings,
                   COUNT(ru.id) as active_referrals
            FROM referral_codes rc
            JOIN customers c ON rc.customer_id = c.id
            LEFT JOIN referral_usage ru ON rc.customer_id = ru.referrer_id AND ru.status = 'completed'
            WHERE rc.total_referrals > 0
            GROUP BY rc.customer_id
            ORDER BY rc.total_earnings DESC, rc.total_referrals DESC
            LIMIT ?
        """, (limit,))

# Initialize managers
referral_code_generator = ReferralCodeGenerator()
referral_calculator = ReferralRewardCalculator()
referral_wallet = ReferralWalletManager()
referral_tracker = ReferralTracker()