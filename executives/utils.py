import logging
import random
from django.conf import settings
import requests

logger = logging.getLogger(__name__)

def send_otp(mobile_number, otp):
    try:
        response = requests.post(
            "https://2factor.in/API/V1/{}/SMS/{}/{}".format(settings.TWO_FACTOR_API_KEY, mobile_number, otp),
            timeout=5  # Timeout to avoid long waits
        )
    except requests.RequestException as exc:
        logger.error("2Factor OTP request failed for %s: %s", mobile_number, exc)
        return False

    if response.status_code != 200:
        logger.error(
            "2Factor OTP send failed for %s: HTTP %s - %s",
            mobile_number, response.status_code, response.text,
        )
        return False

    # 2Factor returns HTTP 200 even on logical failures (bad key, low
    # balance, invalid number, blocked route) - the real result is in
    # the JSON body's "Status" field.
    try:
        data = response.json()
    except ValueError:
        logger.error("2Factor OTP response not JSON for %s: %s", mobile_number, response.text)
        return False

    if data.get("Status") != "Success":
        logger.error(
            "2Factor OTP send failed for %s: %s",
            mobile_number, data.get("Details", data),
        )
        return False

    return True


def normalize_phone_number(mobile_number):
    """
    Normalize phone number to a standard format for comparison.
    Handles formats like: 918086851333, +918086851333, 8086851333
    Returns normalized format: +918086851333
    """
    if not mobile_number:
        return None
    
    # Remove all non-digit characters
    digits = ''.join(filter(str.isdigit, str(mobile_number)))
    
    # If no digits found, return None
    if not digits:
        return None
    
    # If less than 10 digits, it's invalid
    if len(digits) < 10:
        return None
    
    # If 10 digits, add country code
    if len(digits) == 10:
        digits = '91' + digits
    
    # Return in +91XXXXXXXXXX format
    if len(digits) == 12 and digits.startswith('91'):
        return '+' + digits
    
    # If already has + at start, just ensure it's correct
    if mobile_number.startswith('+'):
        return mobile_number
    
    return '+' + digits if len(digits) == 12 else None


def is_test_number(mobile_number):
    """
    Check if the given mobile number is the test number.
    Handles multiple formats of the test number: 918086851333, +918086851333, 8086851333
    """
    normalized = normalize_phone_number(mobile_number)
    test_number_normalized = normalize_phone_number("918086851333")
    return normalized == test_number_normalized
