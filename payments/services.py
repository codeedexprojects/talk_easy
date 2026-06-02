"""
Payment service layer for Razorpay integration

This module contains all business logic for payment processing,
following SOLID principles and ensuring testability.
"""

import razorpay
import hmac
import hashlib
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import UserRecharge, RechargePlan, WebhookEvent
from .exceptions import (
    InvalidSignatureException,
    OrderNotFoundException,
    PaymentAlreadyProcessedException,
    InsufficientBalanceException
)

logger = logging.getLogger('payments')

# Initialize Razorpay client
razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)


class RazorpayService:
    """Service class for Razorpay payment operations"""

    @staticmethod
    def create_order(user, plan):
        """
        Create a Razorpay order for the given user and plan
        
        Args:
            user: UserProfile instance
            plan: RechargePlan instance
            
        Returns:
            dict: Order details and UserRecharge instance
            
        Raises:
            Exception: If order creation fails
        """
        logger.info(f"Creating Razorpay order for user {user.id}, plan {plan.id}")
        
        # Ensure user has stats
        from users.models import UserStats
        if not hasattr(user, 'stats'):
            logger.warning(f"User {user.id} missing stats, creating now")
            UserStats.objects.create(user=user)
            user.refresh_from_db()
        
        coins_to_add = plan.get_adjusted_coin_package()
        amount_to_pay = plan.calculate_final_price()
        razorpay_amount = int(amount_to_pay * 100)  # Convert to paise
        
        try:
            # Log Razorpay configuration (without exposing secrets)
            logger.info(f"Using Razorpay Key ID: {settings.RAZORPAY_KEY_ID[:12]}...")
            logger.info(f"Order details - Amount: ₹{amount_to_pay}, Coins: {coins_to_add}")
            
            # Create Razorpay order
            razorpay_order = razorpay_client.order.create({
                "amount": razorpay_amount,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "user_id": str(user.id),
                    "plan_id": str(plan.id),
                    "plan_name": plan.plan_name,
                    "coins_to_add": coins_to_add
                }
            })
            
            logger.info(f"Razorpay order created: {razorpay_order['id']}")
            
            # Create UserRecharge record with order ID
            recharge = UserRecharge.objects.create(
                user=user,
                plan=plan,
                coins_added=coins_to_add,
                amount_paid=amount_to_pay,
                razorpay_order_id=razorpay_order["id"],
                payment_status="pending",
                is_successful=False
            )
            
            logger.info(f"UserRecharge record created: {recharge.id}")
            
            return {
                "recharge_id": recharge.id,
                "order_id": razorpay_order["id"],
                "amount": float(amount_to_pay),
                "currency": "INR",
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "coins_to_add": coins_to_add,
            }
            
        except razorpay.errors.BadRequestError as e:
            logger.error(f"Razorpay Bad Request Error: {str(e)}", exc_info=True)
            logger.error(f"Error details - Status Code: {e.status_code if hasattr(e, 'status_code') else 'N/A'}")
            raise Exception(f"Razorpay API Error: {str(e)}")
        except razorpay.errors.GatewayError as e:
            logger.error(f"Razorpay Gateway Error (Network issue): {str(e)}", exc_info=True)
            raise Exception(f"Payment gateway connectivity issue: {str(e)}")
        except razorpay.errors.ServerError as e:
            logger.error(f"Razorpay Server Error: {str(e)}", exc_info=True)
            raise Exception(f"Payment gateway server error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error creating Razorpay order: {type(e).__name__} - {str(e)}", exc_info=True)
            logger.error(f"User ID: {user.id}, Plan ID: {plan.id}, Amount: {razorpay_amount} paise")
            raise

    @staticmethod
    def verify_payment_signature(order_id, payment_id, signature):
        """
        Verify Razorpay payment signature
        
        Args:
            order_id: Razorpay order ID
            payment_id: Razorpay payment ID
            signature: Signature from Razorpay
            

        Returns:
            bool: True if signature is valid
            
        Raises:
            InvalidSignatureException: If signature is invalid
        """
        try:
            generated_signature = hmac.new(
                settings.RAZORPAY_KEY_SECRET.encode(),
                f"{order_id}|{payment_id}".encode(),
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(generated_signature, signature)
            
            if not is_valid:
                logger.warning(f"Invalid signature for order {order_id}")
                raise InvalidSignatureException("Payment signature verification failed")
            
            logger.info(f"Signature verified successfully for order {order_id}")
            return True
            
            
        except Exception as e:
            logger.error(f"Signature verification error: {str(e)}", exc_info=True)
            raise InvalidSignatureException(str(e))

    @staticmethod
    @transaction.atomic
    def process_successful_payment(order_id, payment_id, signature):
        """
        Process a successful payment and update user balance
        
        Args:
            order_id: Razorpay order ID
            payment_id: Razorpay payment ID
            signature: Payment signature
            
        Returns:
            dict: Updated recharge and balance information
            
        Raises:
            OrderNotFoundException: If order not found
            PaymentAlreadyProcessedException: If already processed
        """
        logger.info(f"Processing successful payment for order {order_id}")
        
        # Verify signature first
        RazorpayService.verify_payment_signature(order_id, payment_id, signature)
        
        try:
            # Find the recharge by order ID (not latest)
            recharge = UserRecharge.objects.select_for_update().get(
                razorpay_order_id=order_id
            )
        except UserRecharge.DoesNotExist:
            logger.error(f"UserRecharge not found for order {order_id}")
            raise OrderNotFoundException(f"No recharge found for order {order_id}")
        
        # Check if already processed (idempotency)
        if recharge.is_successful and recharge.payment_status == "successful":
            logger.warning(f"Payment already processed for order {order_id}")
            raise PaymentAlreadyProcessedException("Payment already processed")
        
        # Mark payment as successful
        recharge.mark_as_successful(payment_id=payment_id, signature=signature)
        
        logger.info(
            f"Payment processed successfully. User {recharge.user.id} received "
            f"{recharge.coins_added} coins. New balance: {recharge.user.stats.coin_balance}"
        )
        
        return {
            "message": "Payment verified and recharge successful",
            "recharge_id": recharge.id,
            "coins_added": recharge.coins_added,
            "amount_paid": float(recharge.amount_paid),
            "current_coin_balance": recharge.user.stats.coin_balance
        }

    @staticmethod
    @transaction.atomic
    def process_failed_payment(order_id, reason=""):
        """
        Mark a payment as failed
        
        Args:
            order_id: Razorpay order ID
            reason: Failure reason
        """
        logger.info(f"Processing failed payment for order {order_id}: {reason}")
        
        try:
            recharge = UserRecharge.objects.select_for_update().get(
                razorpay_order_id=order_id
            )
            recharge.mark_as_failed()
            logger.info(f"Payment marked as failed for order {order_id}")
        except UserRecharge.DoesNotExist:
            logger.error(f"UserRecharge not found for failed order {order_id}")

    @staticmethod
    def verify_webhook_signature(webhook_body, signature):
        """
        Verify webhook signature from Razorpay
        
        Args:
            webhook_body: Raw webhook body
            signature: X-Razorpay-Signature header
            
        Returns:
            bool: True if signature is valid
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET:
            logger.warning("RAZORPAY_WEBHOOK_SECRET not configured")
            return False
        
        try:
            generated_signature = hmac.new(
                settings.RAZORPAY_WEBHOOK_SECRET.encode(),
                webhook_body.encode() if isinstance(webhook_body, str) else webhook_body,
                hashlib.sha256
            ).hexdigest()
            
            is_valid = hmac.compare_digest(generated_signature, signature)
            
            if not is_valid:
                logger.warning("Invalid webhook signature")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Webhook signature verification error: {str(e)}", exc_info=True)
            return False


class PaymentWebhookService:
    """Service class for processing Razorpay webhooks"""

    @staticmethod
    @transaction.atomic
    def handle_webhook(event_type, payload):
        """
        Handle incoming webhook event from Razorpay
        
        Args:
            event_type: Type of event (e.g., 'payment.captured')
            payload: Full webhook payload
            
        Returns:
            bool: True if processed successfully
        """
        event_id = payload.get('event_id') or payload.get('id', '')
        logger.info(f"Processing webhook event: {event_type} (ID: {event_id})")
        
        # Check for duplicate webhook (idempotency)
        if event_id and WebhookEvent.objects.filter(event_id=event_id).exists():
            logger.info(f"Duplicate webhook event {event_id}, skipping")
            return True
        
        # Store webhook event
        webhook_event = WebhookEvent.objects.create(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            processed=False
        )
        
        try:
            # Route to appropriate handler
            if event_type == 'payment.captured':
                PaymentWebhookService._handle_payment_captured(payload)
            elif event_type == 'payment.failed':
                PaymentWebhookService._handle_payment_failed(payload)
            elif event_type == 'order.paid':
                PaymentWebhookService._handle_order_paid(payload)
            else:
                logger.info(f"Unhandled webhook event type: {event_type}")
            
            # Mark as processed
            webhook_event.processed = True
            webhook_event.processed_at = timezone.now()
            webhook_event.save()
            
            logger.info(f"Webhook event {event_id} processed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error processing webhook {event_id}: {str(e)}", exc_info=True)
            webhook_event.error_message = str(e)
            webhook_event.save()
            return False

    @staticmethod
    def _handle_payment_captured(payload):
        """Handle payment.captured event"""
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = payment_entity.get('order_id')
        payment_id = payment_entity.get('id')
        
        if not order_id or not payment_id:
            logger.error("Missing order_id or payment_id in webhook payload")
            return
        
        logger.info(f"Payment captured: order={order_id}, payment={payment_id}")
        
        try:
            recharge = UserRecharge.objects.select_for_update().get(
                razorpay_order_id=order_id
            )
            
            if not recharge.is_successful:
                recharge.mark_as_successful(payment_id=payment_id)
                recharge.webhook_received_at = timezone.now()
                recharge.save(update_fields=['webhook_received_at'])
                logger.info(f"Payment processed via webhook for order {order_id}")
            else:
                logger.info(f"Payment already processed for order {order_id}")
                
        except UserRecharge.DoesNotExist:
            logger.error(f"UserRecharge not found for order {order_id}")

    @staticmethod
    def _handle_payment_failed(payload):
        """Handle payment.failed event"""
        payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = payment_entity.get('order_id')
        error_description = payment_entity.get('error_description', 'Unknown error')
        
        if not order_id:
            logger.error("Missing order_id in failed payment webhook")
            return
        
        logger.info(f"Payment failed: order={order_id}, reason={error_description}")
        RazorpayService.process_failed_payment(order_id, reason=error_description)

    @staticmethod
    def _handle_order_paid(payload):
        """Handle order.paid event"""
        order_entity = payload.get('payload', {}).get('order', {}).get('entity', {})
        order_id = order_entity.get('id')
        
        if not order_id:
            logger.error("Missing order_id in order.paid webhook")
            return
        
        logger.info(f"Order paid: {order_id}")
        # Additional verification can be done here if needed
