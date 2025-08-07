# -*- coding: utf-8 -*-
"""
Discount code system for Master Bot
Handles discount codes, validation, and usage tracking
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from database import execute_db, query_db

logger = logging.getLogger(__name__)

class DiscountCodeManager:
    """Manager for discount codes"""
    
    @staticmethod
    def create_discount_code(
        code: str,
        discount_percent: int = 0,
        discount_amount: int = 0,
        max_uses: int = -1,
        valid_for: str = 'both',
        min_amount: int = 0,
        expires_at: str = None,
        created_by: int = None
    ) -> Optional[int]:
        """Create a new discount code"""
        
        # Validate parameters
        if not code or len(code.strip()) < 3:
            return None
        
        if discount_percent <= 0 and discount_amount <= 0:
            return None
        
        if discount_percent > 100:
            discount_percent = 100
        
        try:
            discount_id = execute_db("""
                INSERT INTO discount_codes 
                (code, discount_percent, discount_amount, max_uses, valid_for, 
                 min_amount, expires_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                code.upper().strip(),
                discount_percent,
                discount_amount,
                max_uses,
                valid_for,
                min_amount,
                expires_at,
                created_by
            ))
            
            logger.info(f"Created discount code: {code}")
            return discount_id
            
        except Exception as e:
            logger.error(f"Failed to create discount code {code}: {e}")
            return None
    
    @staticmethod
    def validate_discount_code(
        code: str,
        customer_id: int,
        amount: int,
        transaction_type: str = 'purchase'
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate discount code
        
        Returns:
            (is_valid, message, discount_info)
        """
        
        if not code or not code.strip():
            return False, "کد تخفیف وارد نشده است", None
        
        # Get discount code info
        discount = query_db("""
            SELECT * FROM discount_codes 
            WHERE code = ? AND is_active = 1
        """, (code.upper().strip(),), one=True)
        
        if not discount:
            return False, "کد تخفیف معتبر نیست", None
        
        # Check expiration
        if discount['expires_at']:
            try:
                expires_at = datetime.fromisoformat(discount['expires_at'])
                if datetime.now() > expires_at:
                    return False, "کد تخفیف منقضی شده است", None
            except:
                pass
        
        # Check usage limit
        if discount['max_uses'] > 0 and discount['used_count'] >= discount['max_uses']:
            return False, "کد تخفیف به حد مجاز استفاده رسیده است", None
        
        # Check minimum amount
        if amount < discount['min_amount']:
            return False, f"حداقل مبلغ برای این کد تخفیف {discount['min_amount']:,} تومان است", None
        
        # Check valid_for (purchase/renewal/both)
        if discount['valid_for'] not in ['both', transaction_type]:
            valid_text = {
                'purchase': 'خرید جدید',
                'renewal': 'تمدید',
                'both': 'خرید و تمدید'
            }
            return False, f"این کد تخفیف فقط برای {valid_text.get(discount['valid_for'], 'نامشخص')} معتبر است", None
        
        # Check if customer has already used this code
        usage = query_db("""
            SELECT id FROM discount_code_usage 
            WHERE discount_code_id = ? AND customer_id = ?
        """, (discount['id'], customer_id), one=True)
        
        if usage:
            return False, "شما قبلاً از این کد تخفیف استفاده کرده‌اید", None
        
        return True, "کد تخفیف معتبر است", discount
    
    @staticmethod
    def calculate_discount(discount_info: Dict, original_amount: int) -> int:
        """Calculate discount amount"""
        
        if not discount_info:
            return 0
        
        discount_amount = 0
        
        # Percentage discount
        if discount_info['discount_percent'] > 0:
            discount_amount = int((original_amount * discount_info['discount_percent']) / 100)
        
        # Fixed amount discount
        if discount_info['discount_amount'] > 0:
            discount_amount = max(discount_amount, discount_info['discount_amount'])
        
        # Don't let discount exceed original amount
        discount_amount = min(discount_amount, original_amount)
        
        return discount_amount
    
    @staticmethod
    def apply_discount_code(
        discount_code_id: int,
        customer_id: int,
        payment_id: int,
        discount_amount: int
    ) -> bool:
        """Apply discount code and record usage"""
        
        try:
            # Record usage
            execute_db("""
                INSERT INTO discount_code_usage 
                (discount_code_id, customer_id, payment_id, discount_amount)
                VALUES (?, ?, ?, ?)
            """, (discount_code_id, customer_id, payment_id, discount_amount))
            
            # Update usage count
            execute_db("""
                UPDATE discount_codes 
                SET used_count = used_count + 1 
                WHERE id = ?
            """, (discount_code_id,))
            
            logger.info(f"Applied discount code {discount_code_id} for customer {customer_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to apply discount code: {e}")
            return False
    
    @staticmethod
    def get_discount_codes(active_only: bool = True) -> List[Dict]:
        """Get all discount codes"""
        
        query = "SELECT * FROM discount_codes"
        params = ()
        
        if active_only:
            query += " WHERE is_active = 1"
        
        query += " ORDER BY created_at DESC"
        
        return query_db(query, params)
    
    @staticmethod
    def get_discount_code_usage(discount_code_id: int) -> List[Dict]:
        """Get usage history for a discount code"""
        
        return query_db("""
            SELECT dcu.*, c.first_name, c.username, c.user_id, p.amount
            FROM discount_code_usage dcu
            LEFT JOIN customers c ON dcu.customer_id = c.id
            LEFT JOIN payments p ON dcu.payment_id = p.id
            WHERE dcu.discount_code_id = ?
            ORDER BY dcu.used_at DESC
        """, (discount_code_id,))
    
    @staticmethod
    def deactivate_discount_code(discount_code_id: int) -> bool:
        """Deactivate a discount code"""
        
        try:
            execute_db("""
                UPDATE discount_codes 
                SET is_active = 0 
                WHERE id = ?
            """, (discount_code_id,))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to deactivate discount code: {e}")
            return False
    
    @staticmethod
    def get_customer_discount_usage(customer_id: int) -> List[Dict]:
        """Get discount codes used by a customer"""
        
        return query_db("""
            SELECT dcu.*, dc.code, dc.discount_percent, dc.discount_amount
            FROM discount_code_usage dcu
            LEFT JOIN discount_codes dc ON dcu.discount_code_id = dc.id
            WHERE dcu.customer_id = ?
            ORDER BY dcu.used_at DESC
        """, (customer_id,))

class BroadcastManager:
    """Manager for broadcast messages"""
    
    @staticmethod
    def get_all_customers() -> List[Dict]:
        """Get all customers for broadcast"""
        
        return query_db("""
            SELECT user_id, first_name, username, status 
            FROM customers 
            WHERE status = 'active'
            ORDER BY created_at DESC
        """)
    
    @staticmethod
    def get_customers_with_active_subscriptions() -> List[Dict]:
        """Get customers with active subscriptions"""
        
        return query_db("""
            SELECT DISTINCT c.user_id, c.first_name, c.username
            FROM customers c
            INNER JOIN subscriptions s ON c.id = s.customer_id
            WHERE c.status = 'active' AND s.status = 'active'
            ORDER BY c.created_at DESC
        """)
    
    @staticmethod
    def get_customers_with_expired_subscriptions() -> List[Dict]:
        """Get customers with expired subscriptions"""
        
        return query_db("""
            SELECT DISTINCT c.user_id, c.first_name, c.username
            FROM customers c
            INNER JOIN subscriptions s ON c.id = s.customer_id
            WHERE c.status = 'active' AND s.status = 'expired'
            ORDER BY c.created_at DESC
        """)

class NotesManager:
    """Manager for customer notes"""
    
    @staticmethod
    def add_note(customer_id: int, note: str, created_by: int, is_important: bool = False) -> Optional[int]:
        """Add a note for a customer"""
        
        if not note or not note.strip():
            return None
        
        try:
            note_id = execute_db("""
                INSERT INTO customer_notes (customer_id, note, created_by, is_important)
                VALUES (?, ?, ?, ?)
            """, (customer_id, note.strip(), created_by, is_important))
            
            logger.info(f"Added note for customer {customer_id}")
            return note_id
            
        except Exception as e:
            logger.error(f"Failed to add note: {e}")
            return None
    
    @staticmethod
    def get_customer_notes(customer_id: int) -> List[Dict]:
        """Get all notes for a customer"""
        
        return query_db("""
            SELECT cn.*, c.first_name as created_by_name, c.username as created_by_username
            FROM customer_notes cn
            LEFT JOIN customers c ON cn.created_by = c.id
            WHERE cn.customer_id = ?
            ORDER BY cn.is_important DESC, cn.created_at DESC
        """, (customer_id,))
    
    @staticmethod
    def delete_note(note_id: int, admin_id: int) -> bool:
        """Delete a note (only by admin or creator)"""
        
        try:
            # Check if note exists and get creator info
            note = query_db("""
                SELECT created_by FROM customer_notes WHERE id = ?
            """, (note_id,), one=True)
            
            if not note:
                return False
            
            # Allow deletion by creator or admin
            from config import config
            if note['created_by'] == admin_id or admin_id == config.MASTER_ADMIN_ID:
                execute_db("DELETE FROM customer_notes WHERE id = ?", (note_id,))
                logger.info(f"Deleted note {note_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete note: {e}")
            return False

# Initialize managers
discount_manager = DiscountCodeManager()
broadcast_manager = BroadcastManager()
notes_manager = NotesManager()