import sys
import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talk_easy.settings')
django.setup()

from executives.models import Executive, ExecutiveStats
from calls.models import AgoraCallHistory
import logging

try:
    c = AgoraCallHistory.objects.filter(status="ended").last()
    print("Call ID:", c.id)
    print("amount_per_min:", getattr(c, 'amount_per_min', None))
    print("executive_earnings:", getattr(c, 'executive_earnings', None))
    print("duration:", getattr(c, 'duration_seconds', None))
    print("executive stats:")
    s = c.executive.stats
    print("total earnings:", getattr(s, 'total_earnings', None))
    print("talk seconds:", getattr(s, 'total_talk_seconds', None))
except Exception as e:
    import traceback
    traceback.print_exc()
