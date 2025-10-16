# calls/models.py
from django.db import models, transaction
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.conf import settings
from users.models import UserProfile
from executives.models import Executive,ExecutiveStats
from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone

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
    coins_per_second = models.FloatField(default=3)
    amount_per_min = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    last_heartbeat = models.DateTimeField(null=True, blank=True)  
    last_coin_update_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    executive_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

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
        if self.end_time:
            return  # Call already ended

        now_time = timezone.now()
        self.end_time = now_time

        # Calculate call duration
        base_start = self.joined_at or self.start_time
        self.duration = (now_time - base_start) if base_start else timedelta()
        duration_seconds = int(self.duration.total_seconds())
        self.duration_seconds = duration_seconds

        # ----------------------------
        # Deduct coins from user
        # ----------------------------
        coins_to_deduct = int(Decimal(duration_seconds) * Decimal(str(self.coins_per_second)))
        self.coins_deducted = coins_to_deduct

        if hasattr(self.user, "stats"):
            user_stats = self.user.stats
            user_stats.coin_balance = max(0, user_stats.coin_balance - coins_to_deduct)
            user_stats.total_calls += 1
            user_stats.total_call_seconds += duration_seconds
            if self.end_time.date() == timezone.now().date():
                user_stats.total_call_seconds_today += duration_seconds
            user_stats.save(update_fields=[
                "coin_balance",
                "total_calls",
                "total_call_seconds",
                "total_call_seconds_today"
            ])

        earnings = Decimal("0.0")
        if hasattr(self.executive, "stats"):
            exec_stats = self.executive.stats

            # Increment picked calls
            exec_stats.total_picked_calls += 1

            # Talk/duration
            exec_stats.total_talk_seconds_today += duration_seconds
            exec_stats.total_talk_seconds += duration_seconds  # all-time
            if getattr(self.executive, "is_online", False):
                exec_stats.total_on_duty_seconds += duration_seconds

            # Calculate earnings
            amount_per_second = (Decimal(str(self.amount_per_min)) / Decimal("60")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            earnings = (Decimal(duration_seconds) * amount_per_second).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            self.executive_earnings = earnings

            # Update executive stats
            exec_stats.total_earnings += earnings
            if self.end_time.date() == timezone.now().date():
                exec_stats.earnings_today += earnings
            exec_stats.vault_Balance += int(earnings)
            exec_stats.pending_payout += earnings
            exec_stats.save(update_fields=[
                "total_picked_calls",
                "total_talk_seconds",
                "total_talk_seconds_today",
                "total_on_duty_seconds",
                "total_earnings",
                "earnings_today",
                "vault_Balance",
                "pending_payout"
            ])

        if hasattr(self.executive, "on_call"):
            self.executive.on_call = False
            self.executive.save(update_fields=["on_call"])

    def deduct_coins(self, coins):
        if self.user.coin_balance <= 0:
            self.end_call(ender="system")
            return False

        # Deduct coins
        self.user.coin_balance -= coins
        self.user.save(update_fields=["coin_balance"])

        if self.user.coin_balance <= 0:
            self.end_call(ender="system")
            return False
        return True



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


class CallRating(models.Model):
    executive = models.ForeignKey('executives.Executive', on_delete=models.CASCADE, related_name="call_ratings")
    user = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE, related_name="call_ratings")
    execallhistory = models.ForeignKey(AgoraCallHistory, on_delete=models.CASCADE, related_name="ratings")
    stars = models.PositiveSmallIntegerField()
    comment = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"Rating for {self.executive} by {self.user} - {self.stars} Stars"
    