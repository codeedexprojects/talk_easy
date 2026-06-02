import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')
django.setup()

from calls.models import AgoraCallHistory
import math

calls = AgoraCallHistory.objects.filter(status="ended").order_by('-id')[:5]
for c in calls:
    print(f"Call {c.id}: status={c.status}, duration_seconds={c.duration_seconds}")
    print(f"  start_time: {c.start_time}")
    print(f"  joined_at: {c.joined_at}")
    print(f"  end_time: {c.end_time}")
    print("---")
