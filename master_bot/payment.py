# -*- coding: utf-8 -*-
import requests
import logging
from typing import Dict, Tuple, Optional
from config import config
from database import execute_db

logger = logging.getLogger(__name__)

class ZarinPalPayment:
    """ZarinPal payment gateway integration"""
    
    def __init__(self):
        self.merchant_id = config.ZARINPAL_MERCHANT_ID
        self.base_url = "https://api.zarinpal.com/pg/v4/payment/"
        self.gateway_url = "https://www.zarinpal.com/pg/StartPay/"
    
    async def create_payment(self, amount: int, description: str, callback_url: str = None) -> Tuple[Optional[str], Optional[str]]:
        """Create payment request"""
        if not self.merchant_id:
            logger.error("ZarinPal merchant ID not configured")
            return None, None
        
        if not callback_url:
            callback_url = "https://your-domain.com/verify"  # You should set this
        
        data = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "description": description,
            "callback_url": callback_url
        }
        
        try:
            response = requests.post(f"{self.base_url}request.json", json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("data", {}).get("code") == 100:
                authority = result["data"]["authority"]
                payment_url = f"{self.gateway_url}{authority}"
                
                logger.info(f"ZarinPal payment created: {authority}")
                return payment_url, authority
            else:
                logger.error(f"ZarinPal payment creation failed: {result}")
                return None, None
                
        except requests.RequestException as e:
            logger.error(f"ZarinPal request failed: {e}")
            return None, None
        except Exception as e:
            logger.error(f"ZarinPal unexpected error: {e}")
            return None, None
    
    async def verify_payment(self, authority: str, amount: int) -> Dict:
        """Verify payment"""
        if not self.merchant_id:
            return {"status": "error", "message": "Merchant ID not configured"}
        
        data = {
            "merchant_id": self.merchant_id,
            "amount": amount,
            "authority": authority
        }
        
        try:
            response = requests.post(f"{self.base_url}verify.json", json=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("data", {}).get("code") == 100:
                ref_id = result["data"]["ref_id"]
                return {
                    "status": "success",
                    "ref_id": ref_id,
                    "message": "Payment verified successfully"
                }
            elif result.get("data", {}).get("code") == 101:
                return {
                    "status": "success",
                    "message": "Payment already verified"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Verification failed: {result.get('errors', 'Unknown error')}"
                }
                
        except requests.RequestException as e:
            logger.error(f"ZarinPal verification request failed: {e}")
            return {"status": "error", "message": "Network error during verification"}
        except Exception as e:
            logger.error(f"ZarinPal verification unexpected error: {e}")
            return {"status": "error", "message": "Unexpected error during verification"}

class IDPayPayment:
    """IDPay payment gateway integration"""
    
    def __init__(self):
        self.api_key = config.IDPAY_API_KEY
        self.base_url = "https://api.idpay.ir/v1.1/payment"
    
    async def create_payment(self, amount: int, description: str, callback_url: str = None) -> Tuple[Optional[str], Optional[str]]:
        """Create payment request"""
        if not self.api_key:
            logger.error("IDPay API key not configured")
            return None, None
        
        if not callback_url:
            callback_url = "https://your-domain.com/verify"  # You should set this
        
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "order_id": f"order_{int(time.time())}",
            "amount": amount,
            "desc": description,
            "callback": callback_url
        }
        
        try:
            response = requests.post(self.base_url, json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if "link" in result:
                payment_url = result["link"]
                order_id = result["id"]
                
                logger.info(f"IDPay payment created: {order_id}")
                return payment_url, order_id
            else:
                logger.error(f"IDPay payment creation failed: {result}")
                return None, None
                
        except requests.RequestException as e:
            logger.error(f"IDPay request failed: {e}")
            return None, None
        except Exception as e:
            logger.error(f"IDPay unexpected error: {e}")
            return None, None
    
    async def verify_payment(self, order_id: str) -> Dict:
        """Verify payment"""
        if not self.api_key:
            return {"status": "error", "message": "API key not configured"}
        
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "id": order_id,
            "order_id": order_id
        }
        
        try:
            response = requests.post(f"{self.base_url}/verify", json=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") == 100:  # Success
                return {
                    "status": "success",
                    "track_id": result.get("track_id"),
                    "message": "Payment verified successfully"
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Verification failed: {result.get('message', 'Unknown error')}"
                }
                
        except requests.RequestException as e:
            logger.error(f"IDPay verification request failed: {e}")
            return {"status": "error", "message": "Network error during verification"}
        except Exception as e:
            logger.error(f"IDPay verification unexpected error: {e}")
            return {"status": "error", "message": "Unexpected error during verification"}

class PaymentService:
    """Main payment service that handles multiple payment gateways"""
    
    def __init__(self):
        self.zarinpal = ZarinPalPayment()
        self.idpay = IDPayPayment()
        
        # Determine which gateway to use based on configuration
        if config.ZARINPAL_MERCHANT_ID:
            self.primary_gateway = "zarinpal"
        elif config.IDPAY_API_KEY:
            self.primary_gateway = "idpay"
        else:
            self.primary_gateway = None
            logger.warning("No payment gateway configured")
    
    async def create_payment(self, payment_data: Dict) -> Tuple[Optional[str], Optional[str]]:
        """Create payment using available gateway"""
        if not self.primary_gateway:
            logger.error("No payment gateway available")
            return None, None
        
        customer_id = payment_data['customer_id']
        amount = payment_data['amount']
        description = payment_data.get('description', 'Payment for VPN Bot')
        
        # Create payment record in database
        payment_id = execute_db(
            "INSERT INTO payments (customer_id, amount, payment_method, status) VALUES (?, ?, ?, ?)",
            (customer_id, amount, self.primary_gateway, 'pending')
        )
        
        if not payment_id:
            logger.error("Failed to create payment record in database")
            return None, None
        
        # Create payment with gateway
        if self.primary_gateway == "zarinpal":
            payment_url, authority = await self.zarinpal.create_payment(amount, description)
            if authority:
                # Update payment record with authority
                execute_db(
                    "UPDATE payments SET authority = ? WHERE id = ?",
                    (authority, payment_id)
                )
                return payment_url, authority
        
        elif self.primary_gateway == "idpay":
            payment_url, order_id = await self.idpay.create_payment(amount, description)
            if order_id:
                # Update payment record with order_id
                execute_db(
                    "UPDATE payments SET transaction_id = ? WHERE id = ?",
                    (order_id, payment_id)
                )
                return payment_url, order_id
        
        # If we reach here, payment creation failed
        execute_db(
            "UPDATE payments SET status = ? WHERE id = ?",
            ('failed', payment_id)
        )
        
        return None, None
    
    async def verify_payment(self, authority_or_order_id: str) -> Dict:
        """Verify payment using appropriate gateway"""
        if not self.primary_gateway:
            return {"status": "error", "message": "No payment gateway available"}
        
        # Get payment record from database
        if self.primary_gateway == "zarinpal":
            payment = query_db(
                "SELECT * FROM payments WHERE authority = ? AND status = 'pending'",
                (authority_or_order_id,), one=True
            )
        else:  # idpay
            payment = query_db(
                "SELECT * FROM payments WHERE transaction_id = ? AND status = 'pending'",
                (authority_or_order_id,), one=True
            )
        
        if not payment:
            return {"status": "error", "message": "Payment record not found"}
        
        # Verify with gateway
        if self.primary_gateway == "zarinpal":
            result = await self.zarinpal.verify_payment(authority_or_order_id, payment['amount'])
        else:  # idpay
            result = await self.idpay.verify_payment(authority_or_order_id)
        
        # Update payment status in database
        if result['status'] == 'success':
            execute_db(
                "UPDATE payments SET status = ?, payment_date = CURRENT_TIMESTAMP WHERE id = ?",
                ('paid', payment['id'])
            )
            
            # Update customer total_paid
            execute_db(
                "UPDATE customers SET total_paid = total_paid + ? WHERE id = ?",
                (payment['amount'], payment['customer_id'])
            )
            
            logger.info(f"Payment {payment['id']} verified successfully")
        else:
            execute_db(
                "UPDATE payments SET status = ? WHERE id = ?",
                ('failed', payment['id'])
            )
            logger.warning(f"Payment {payment['id']} verification failed")
        
        return result
    
    def get_payment_status(self, payment_id: int) -> Optional[Dict]:
        """Get payment status from database"""
        return query_db("SELECT * FROM payments WHERE id = ?", (payment_id,), one=True)
    
    def get_customer_payments(self, customer_id: int) -> list:
        """Get all payments for a customer"""
        return query_db(
            "SELECT * FROM payments WHERE customer_id = ? ORDER BY created_at DESC",
            (customer_id,)
        )

# Initialize payment service
payment_service = PaymentService()

# Import time for order_id generation
import time
from database import query_db