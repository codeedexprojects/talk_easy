import random
from django.conf import settings
import requests

def send_otp(mobile_number, otp):
    try:
        response = requests.post(
            "https://2factor.in/API/V1/{}/SMS/{}/{}".format(settings.TWO_FACTOR_API_KEY, mobile_number, otp),
            timeout=5  # Timeout to avoid long waits
        )
        return response.status_code == 200
    except requests.RequestException:
        return False
