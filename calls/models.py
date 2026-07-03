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

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ringing", db_index=True)
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

    monitor_uid = models.IntegerField(null=True, blank=True)  
    monitor_token = models.CharField(max_length=512, null=True, blank=True)  
    is_monitored = models.BooleanField(default=False)  

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
        self.is_active = True
        self.save(update_fields=["joined_at", "status", "is_active"])

    def _compute_final_duration(self, ended_at):
        base_start = self.joined_at or self.start_time
        return (ended_at - base_start) if ended_at and base_start else timezone.timedelta()

    def end_call(self, ender="client", request_id=None):
        from users.models import UserStats
        from executives.models import Executive, ExecutiveStats

        with transaction.atomic():
            try:
                locked_call = AgoraCallHistory.objects.select_for_update().get(id=self.id)
            except AgoraCallHistory.DoesNotExist:
                return

            if locked_call.status in ["ended", "missed", "cancelled", "rejected"]:
                self.refresh_from_db()
                return

            now_time = timezone.now()
            self.end_time = now_time

            if not self.joined_at:
                self.status = "cancelled" if ender in ["user", "client"] else "missed"
                self.duration = timedelta()
                self.duration_seconds = 0
                self.is_active = False
                self.ended_by = ender
                if request_id:
                    self.end_request_id = request_id
                
                if hasattr(self.executive, "on_call"):
                    exec_obj = Executive.objects.select_for_update().get(id=self.executive.id)
                    exec_obj.on_call = False
                    exec_obj.save(update_fields=["on_call"])
                    self.executive.on_call = False
                    
                self.save(update_fields=["end_time", "duration", "duration_seconds", "status", "is_active", "ended_by", "end_request_id"])
                return

            base_start = self.joined_at
            self.duration = (now_time - base_start)
            duration_seconds = int(self.duration.total_seconds())
            self.duration_seconds = duration_seconds

            coins_to_deduct = int(Decimal(duration_seconds) * Decimal(str(self.coins_per_second)))
            self.coins_deducted = coins_to_deduct

            if hasattr(self.user, "stats"):
                user_stats = UserStats.objects.select_for_update().get(user=self.user)
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
                from executives.models import GlobalPricing

                exec_stats = ExecutiveStats.objects.select_for_update().get(executive=self.executive)

                exec_stats.total_picked_calls += 1
                exec_stats.total_talk_seconds_today += duration_seconds
                exec_stats.total_talk_seconds += duration_seconds
                if getattr(self.executive, "is_online", False):
                    exec_stats.total_on_duty_seconds += duration_seconds

                # Always use GlobalPricing.default_amount_per_min for earnings calculation.
                global_pricing = GlobalPricing.objects.first()
                global_rate = global_pricing.default_amount_per_min if global_pricing else Decimal("2.0")
                amount_per_second = Decimal(str(global_rate)) / Decimal("60")
                earnings = (Decimal(duration_seconds) * amount_per_second).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                self.executive_earnings = earnings
                self.amount_per_min = global_rate  # store the actual rate used

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
                exec_obj = Executive.objects.select_for_update().get(id=self.executive.id)
                exec_obj.on_call = False
                exec_obj.save(update_fields=["on_call"])
                self.executive.on_call = False

            self.status = "ended"
            self.is_active = False
            self.ended_by = ender
            if request_id:
                self.end_request_id = request_id

            self.save(update_fields=[
                "end_time",
                "duration",
                "duration_seconds",
                "coins_deducted",
                "executive_earnings",
                "amount_per_min",
                "status",
                "is_active",
                "ended_by",
                "end_request_id"
            ])



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

    @staticmethod
    def end_stale_ongoing_calls(stale_after_seconds=25, no_heartbeat_fallback_seconds=300, ringing_timeout_seconds=30):
        """Force-end calls stuck in 'joined'/'ringing'/'pending' that have gone stale.

        Covers app crashes / network drops where neither the client nor the
        Agora webhook ever sends an end signal, so the call and the
        executive's on_call flag would otherwise stay stuck forever. This is
        the server-side authority: it does not trust is_active (which can be
        stale on older/edge-case rows) and instead keys off status + timestamps.

        stale_after_seconds applies only when last_heartbeat is present (i.e.
        the client is actively sending heartbeats) — it's a tight bound because
        we know the signal is fresh. no_heartbeat_fallback_seconds applies when
        last_heartbeat has never been set (older clients that don't send
        heartbeats yet); it must stay generous, since duration/coin billing is
        computed from joined_at and cutting this too short both kills healthy
        calls and undercharges for calls that were actually still running.
        """
        heartbeat_cutoff = timezone.now() - timedelta(seconds=stale_after_seconds)
        fallback_cutoff = timezone.now() - timedelta(seconds=no_heartbeat_fallback_seconds)
        stale_joined_ids = AgoraCallHistory.objects.filter(
            status="joined",
        ).filter(
            models.Q(last_heartbeat__isnull=False, last_heartbeat__lte=heartbeat_cutoff) |
            models.Q(last_heartbeat__isnull=True, joined_at__lte=fallback_cutoff)
        ).values_list("id", flat=True)

        ended = []
        for call_id in stale_joined_ids:
            call = AgoraCallHistory.objects.get(id=call_id)
            call.end_call(ender="system_timeout")
            ended.append(call_id)

        # Never-answered calls: no one joined, and ringing/pending has gone stale.
        ringing_cutoff = timezone.now() - timedelta(seconds=ringing_timeout_seconds)
        stale_ringing_ids = AgoraCallHistory.objects.filter(
            status__in=["ringing", "pending"],
            joined_at__isnull=True,
            start_time__lte=ringing_cutoff,
        ).values_list("id", flat=True)

        for call_id in stale_ringing_ids:
            call = AgoraCallHistory.objects.get(id=call_id)
            call.end_call(ender="system_timeout")
            ended.append(call_id)

        return ended


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
    