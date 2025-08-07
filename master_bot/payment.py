# -*- coding: utf-8 -*-
import requests
import logging
import time
import json
from typing import Dict, Tuple, Optional, List
from config import config
from database import execute_db, query_db

logger = logging.getLogger(__name__)

class AqayPayment:
    """Aqay Payment gateway integration"""
    
    def __init__(self):
        self.api_key = config.AQAY_API_KEY
        self.base_url = config.AQAY_BASE_URL or "https://aqayepardakht.ir/api/v2"
        self.enabled = config.AQAY_ENABLED
    
    async def create_payment(self, amount: int, description: str, callback_url: str = None) -> Tuple[Optional[str], Optional[str]]:
        """Create payment request with Aqay"""
        if not self.enabled or not self.api_key:
            return None, None
        
        if not callback_url:
            callback_url = f"{config.SERVER_HOST}/verify/aqay"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "amount": amount,
            "description": description,
            "callback_url": callback_url,
            "order_id": f"master_bot_{int(time.time())}"
        }
        
        try:
            response = requests.post(f"{self.base_url}/payment/request", json=data, headers=headers, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") == "success":
                payment_url = result["data"]["payment_url"]
                transaction_id = result["data"]["transaction_id"]
                
                logger.info(f"Aqay payment created: {transaction_id}")
                return payment_url, transaction_id
            else:
                logger.error(f"Aqay payment creation failed: {result}")
                return None, None
                
        except requests.RequestException as e:
            logger.error(f"Aqay request failed: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Aqay unexpected error: {e}")
            return None, None
    
    async def verify_payment(self, transaction_id: str) -> Dict:
        """Verify payment with Aqay"""
        if not self.enabled or not self.api_key:
            return {"status": "error", "message": "Aqay not configured"}
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/payment/verify",
                json={"transaction_id": transaction_id},
                headers=headers,
                timeout=15
            )
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") == "success" and result.get("data", {}).get("paid"):
                return {
                    "status": "success",
                    "ref_id": result["data"]["ref_id"],
                    "message": "Payment verified successfully"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Verification failed: {result.get('message', 'Unknown error')}"
                }
                
        except requests.RequestException as e:
            logger.error(f"Aqay verification request failed: {e}")
            return {"status": "error", "message": "Network error during verification"}
        except Exception as e:
            logger.error(f"Aqay verification unexpected error: {e}")
            return {"status": "error", "message": "Unexpected error during verification"}

class CardToCardPayment:
    """Card to card payment management"""
    
    def __init__(self):
        self.enabled = config.CARD_TO_CARD_ENABLED
    
    def get_active_cards(self) -> List[Dict]:
        """Get list of active card numbers"""
        if not self.enabled:
            return []
        
        cards = query_db("""
            SELECT * FROM payment_cards 
            WHERE is_active = 1 
            ORDER BY priority ASC, id ASC
        """)
        
        return cards or []
    
    def create_payment_request(self, amount: int, customer_id: int) -> Optional[Dict]:
        """Create card to card payment request"""
        if not self.enabled:
            return None
        
        active_cards = self.get_active_cards()
        if not active_cards:
            logger.error("No active cards available for card-to-card payment")
            return None
        
        # Select card (round-robin or based on priority)
        selected_card = active_cards[0]  # Simple selection, can be improved
        
        # Create payment record
        payment_id = execute_db("""
            INSERT INTO payments (customer_id, amount, payment_method, status, card_id)
            VALUES (?, ?, 'card_to_card', 'pending', ?)
        """, (customer_id, amount, selected_card['id']))
        
        if payment_id:
            # Generate unique payment code
            payment_code = f"C2C{payment_id:06d}"
            
            execute_db("""
                UPDATE payments SET transaction_id = ? WHERE id = ?
            """, (payment_code, payment_id))
            
            return {
                'payment_id': payment_id,
                'payment_code': payment_code,
                'card_number': selected_card['card_number'],
                'card_name': selected_card['card_name'],
                'amount': amount,
                'instructions': selected_card.get('instructions', '')
            }
        
        return None
    
    def verify_payment(self, payment_code: str) -> Dict:
        """Manual verification for card to card (admin confirms)"""
        payment = query_db("""
            SELECT p.*, c.card_number, c.card_name 
            FROM payments p 
            LEFT JOIN payment_cards c ON p.card_id = c.id 
            WHERE p.transaction_id = ? AND p.payment_method = 'card_to_card'
        """, (payment_code,), one=True)
        
        if not payment:
            return {"status": "error", "message": "Payment not found"}
        
        if payment['status'] == 'paid':
            return {"status": "success", "message": "Payment already confirmed"}
        elif payment['status'] == 'pending':
            return {"status": "pending", "message": "Payment pending admin confirmation"}
        else:
            return {"status": "failed", "message": "Payment failed or cancelled"}

class CryptoPayment:
    """Cryptocurrency payment management"""
    
    def __init__(self):
        self.enabled = config.CRYPTO_ENABLED
        self.dollar_price = self.get_dollar_price()
    
    def get_dollar_price(self) -> float:
        """Get current dollar price set by admin"""
        price_setting = query_db("""
            SELECT value FROM settings WHERE key = 'dollar_price'
        """, one=True)
        
        if price_setting:
            try:
                return float(price_setting['value'])
            except ValueError:
                pass
        
        return config.DEFAULT_DOLLAR_PRICE or 50000.0  # Default fallback
    
    def get_active_wallets(self) -> List[Dict]:
        """Get list of active crypto wallets"""
        if not self.enabled:
            return []
        
        wallets = query_db("""
            SELECT * FROM crypto_wallets 
            WHERE is_active = 1 
            ORDER BY priority ASC, id ASC
        """)
        
        return wallets or []
    
    def calculate_crypto_amount(self, toman_amount: int, crypto_type: str) -> float:
        """Calculate crypto amount based on toman amount"""
        # Convert toman to dollar
        dollar_amount = toman_amount / self.dollar_price
        
        # For now, assume 1:1 USD to crypto (can be improved with real-time rates)
        # You can add specific rates for different cryptocurrencies
        crypto_rates = {
            'USDT': 1.0,
            'BTC': 0.000025,  # Example rate
            'ETH': 0.0004,    # Example rate
            'TRX': 15.0       # Example rate
        }
        
        rate = crypto_rates.get(crypto_type.upper(), 1.0)
        return dollar_amount * rate
    
    def create_payment_request(self, amount: int, customer_id: int, crypto_type: str = None) -> Optional[Dict]:
        """Create crypto payment request"""
        if not self.enabled:
            return None
        
        active_wallets = self.get_active_wallets()
        if not active_wallets:
            logger.error("No active crypto wallets available")
            return None
        
        # Filter by crypto type if specified
        if crypto_type:
            active_wallets = [w for w in active_wallets if w['crypto_type'].upper() == crypto_type.upper()]
            if not active_wallets:
                logger.error(f"No active {crypto_type} wallets available")
                return None
        
        # Select wallet
        selected_wallet = active_wallets[0]
        crypto_amount = self.calculate_crypto_amount(amount, selected_wallet['crypto_type'])
        
        # Create payment record
        payment_id = execute_db("""
            INSERT INTO payments (customer_id, amount, payment_method, status, wallet_id, crypto_amount)
            VALUES (?, ?, 'crypto', 'pending', ?, ?)
        """, (customer_id, amount, selected_wallet['id'], crypto_amount))
        
        if payment_id:
            payment_code = f"CRYPTO{payment_id:06d}"
            
            execute_db("""
                UPDATE payments SET transaction_id = ? WHERE id = ?
            """, (payment_code, payment_id))
            
            return {
                'payment_id': payment_id,
                'payment_code': payment_code,
                'wallet_address': selected_wallet['wallet_address'],
                'crypto_type': selected_wallet['crypto_type'],
                'crypto_amount': crypto_amount,
                'toman_amount': amount,
                'dollar_price': self.dollar_price,
                'network': selected_wallet.get('network', ''),
                'instructions': selected_wallet.get('instructions', '')
            }
        
        return None
    
    def verify_payment(self, payment_code: str) -> Dict:
        """Manual verification for crypto (admin confirms)"""
        payment = query_db("""
            SELECT p.*, w.wallet_address, w.crypto_type, w.network 
            FROM payments p 
            LEFT JOIN crypto_wallets w ON p.wallet_id = w.id 
            WHERE p.transaction_id = ? AND p.payment_method = 'crypto'
        """, (payment_code,), one=True)
        
        if not payment:
            return {"status": "error", "message": "Payment not found"}
        
        if payment['status'] == 'paid':
            return {"status": "success", "message": "Payment already confirmed"}
        elif payment['status'] == 'pending':
            return {"status": "pending", "message": "Payment pending admin confirmation"}
        else:
            return {"status": "failed", "message": "Payment failed or cancelled"}

class PaymentService:
    """Enhanced payment service with multiple payment methods"""
    
    def __init__(self):
        self.aqay = AqayPayment()
        self.card_to_card = CardToCardPayment()
        self.crypto = CryptoPayment()
    
    def get_available_payment_methods(self) -> Dict:
        """Get list of available payment methods"""
        methods = {}
        
        if self.aqay.enabled and self.aqay.api_key:
            methods['aqay'] = {
                'name': 'درگاه آقای پرداخت',
                'icon': '🌐',
                'description': 'پرداخت آنلاین با کارت بانکی',
                'instant': True
            }
        
        if self.card_to_card.enabled and self.card_to_card.get_active_cards():
            methods['card_to_card'] = {
                'name': 'کارت به کارت',
                'icon': '💳',
                'description': 'انتقال وجه مستقیم به کارت',
                'instant': False
            }
        
        if self.crypto.enabled and self.crypto.get_active_wallets():
            methods['crypto'] = {
                'name': 'رمز ارز',
                'icon': '🪙',
                'description': 'پرداخت با ارز دیجیتال',
                'instant': False
            }
        
        return methods
    
    async def create_payment(self, payment_data: Dict) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
        """Create payment using specified method"""
        customer_id = payment_data['customer_id']
        amount = payment_data['amount']
        method = payment_data.get('method', 'aqay')
        description = payment_data.get('description', 'Payment for VPN Bot')
        
        if method == 'aqay':
            payment_url, transaction_id = await self.aqay.create_payment(amount, description)
            if payment_url:
                # Update payment record with transaction_id
                execute_db("""
                    INSERT INTO payments (customer_id, amount, payment_method, status, transaction_id)
                    VALUES (?, ?, 'aqay', 'pending', ?)
                """, (customer_id, amount, transaction_id))
                return payment_url, transaction_id, None
        
        elif method == 'card_to_card':
            payment_info = self.card_to_card.create_payment_request(amount, customer_id)
            if payment_info:
                return None, payment_info['payment_code'], payment_info
        
        elif method == 'crypto':
            crypto_type = payment_data.get('crypto_type')
            payment_info = self.crypto.create_payment_request(amount, customer_id, crypto_type)
            if payment_info:
                return None, payment_info['payment_code'], payment_info
        
        return None, None, None
    
    async def verify_payment(self, transaction_id: str, method: str = None) -> Dict:
        """Verify payment using appropriate method"""
        if not method:
            # Auto-detect method from transaction_id
            if transaction_id.startswith('C2C'):
                method = 'card_to_card'
            elif transaction_id.startswith('CRYPTO'):
                method = 'crypto'
            else:
                method = 'aqay'
        
        if method == 'aqay':
            result = await self.aqay.verify_payment(transaction_id)
        elif method == 'card_to_card':
            result = self.card_to_card.verify_payment(transaction_id)
        elif method == 'crypto':
            result = self.crypto.verify_payment(transaction_id)
        else:
            return {"status": "error", "message": "Unknown payment method"}
        
        # Update payment status in database if successful
        if result.get('status') == 'success':
            payment = query_db("""
                SELECT * FROM payments WHERE transaction_id = ? OR authority = ?
            """, (transaction_id, transaction_id), one=True)
            
            if payment:
                execute_db("""
                    UPDATE payments SET status = 'paid', payment_date = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (payment['id'],))
                
                # Update customer total_paid
                execute_db("""
                    UPDATE customers SET total_paid = total_paid + ? WHERE id = ?
                """, (payment['amount'], payment['customer_id']))
                
                logger.info(f"Payment {payment['id']} verified successfully via {method}")
        
        return result
    
    def get_payment_status(self, payment_id: int) -> Optional[Dict]:
        """Get payment status from database"""
        return query_db("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
    
    def get_customer_payments(self, customer_id: int) -> List[Dict]:
        """Get all payments for a customer"""
        return query_db("""
            SELECT * FROM payments WHERE customer_id = ? ORDER BY created_at DESC
        """, (customer_id,))
    
    def get_pending_payments(self) -> List[Dict]:
        """Get all pending manual payments (card-to-card and crypto)"""
        return query_db("""
            SELECT p.*, c.first_name, c.username, c.user_id,
                   pc.card_number, pc.card_name,
                   cw.wallet_address, cw.crypto_type, p.crypto_amount,
                   p.screenshot_file_id, p.screenshot_caption
            FROM payments p
            LEFT JOIN customers c ON p.customer_id = c.id
            LEFT JOIN payment_cards pc ON p.card_id = pc.id
            LEFT JOIN crypto_wallets cw ON p.wallet_id = cw.id
            WHERE p.status = 'pending' AND p.payment_method IN ('card_to_card', 'crypto')
            ORDER BY p.created_at ASC
        """)

# Initialize payment service
payment_service = PaymentService()