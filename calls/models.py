# calls/models.py
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.conf import settings
from users.models import UserProfile
from executives.models import Executive
from datetime import timedelta

class AgoraCallHistory(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),     
        ("ringing", "Ringing"),     
        ("joined", "Joined"),       
        ("missed", "Missed"),      
        ("ended", "Ended"),         
        ("rejected", "Rejected"), 
        ("cancelled", "Cancelled"),
 
    ]

    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="agora_calls_made")
    executive = models.ForeignKey("executives.Executive", on_delete=models.CASCADE, related_name="agora_calls_received")

    channel_name = models.CharField(max_length=100, db_index=True, unique=True)
    token = models.CharField(max_length=512)              
    executive_token = models.CharField(max_length=512)    

    start_time = models.DateTimeField(auto_now_add=True)
    joined_at = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending", db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    uid = models.IntegerField()                   
    callee_uid = models.IntegerField(null=True, blank=True)

    coins_deducted = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    coins_added = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    last_heartbeat = models.DateTimeField(null=True, blank=True)  
    last_coin_update_time = models.DateTimeField(null=True, blank=True)

    ended_by = models.CharField(max_length=50, null=True, blank=True)  
    end_request_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "channel_name"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.channel_name} ({self.status})"

    def mark_joined(self):
        if not self.joined_at:
            self.joined_at = timezone.now()
        if self.status in ["pending", "ringing"]:
            self.status = "joined"
        self.save(update_fields=["joined_at", "status"])

    def _compute_final_duration(self, ended_at):
        base_start = self.joined_at or self.start_time
        return (ended_at - base_start) if ended_at and base_start else timezone.timedelta()

    def end_call(self, ender="client", request_id=None):
        from django.utils import timezone
        
        if self.end_time:
            return  

        self.end_time = timezone.now()
        if self.joined_at:
            self.duration = self.end_time - self.joined_at

        duration_seconds = self.duration.total_seconds() if self.duration else 0
        coins_to_deduct = int(duration_seconds * 3)  
        self.coins_deducted = coins_to_deduct

        if hasattr(self.user, "coins_balance"):
            self.user.coins_balance = max(0, self.user.coins_balance - coins_to_deduct)
            self.user.save()

        self.is_active = False
        self.status = "ended"
        self.ended_by = ender
        self.end_request_id = request_id
        self.save()

    def mark_missed_calls():
        timeout = timezone.now() - timedelta(seconds=30)
        missed_calls = AgoraCallHistory.objects.filter(
            status="ringing", start_time__lte=timeout, is_active=True
        )
        for call in missed_calls:
            call.status = "missed"
            call.is_active = False
            call.end_time = timezone.now()
            call.save()

