"""
Custom exception classes for payment processing

These exceptions provide clear, specific error handling for payment operations.
"""


class PaymentException(Exception):
    """Base exception for all payment-related errors"""
    pass


class InvalidSignatureException(PaymentException):
    """Raised when Razorpay signature verification fails"""
    pass


class OrderNotFoundException(PaymentException):
    """Raised when a Razorpay order cannot be found"""
    pass


class InsufficientBalanceException(PaymentException):
    """Raised when user has insufficient balance"""
    pass


class PaymentAlreadyProcessedException(PaymentException):
    """Raised when attempting to process an already completed payment"""
    pass


class WebhookProcessingException(PaymentException):
    """Raised when webhook processing fails"""
    pass




