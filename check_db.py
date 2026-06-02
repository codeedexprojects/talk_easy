import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')
django.setup()

from executives.models import Executive, ExecutiveStats
from calls.models import AgoraCallHistory

try:
    exec_obj = Executive.objects.get(id=22)
    print("Found executive:", exec_obj.name)
    stats = exec_obj.stats
    print("Stats talk_seconds:", stats.total_talk_seconds)
    print("Stats total_earnings:", stats.total_earnings)
except Exception as e:
    print("Error:", e)

calls = AgoraCallHistory.objects.filter(executive__id=22, status="ended").order_by('-id')[:2]
for c in calls:
    print(f"Call {c.id}: duration={c.duration_seconds}, exec_earn={c.executive_earnings}, amount_per_min={c.amount_per_min}")
