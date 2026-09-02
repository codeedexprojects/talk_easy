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
    presence_missed_since = models.DateTimeField(
        null=True, blank=True,
        help_text="First time the Agora presence check found neither party in the "
                   "channel; only ends the call once this has held for a confirm "
                   "window, so one momentary blip doesn't kill a healthy call."
    )
    presence_partial_since = models.DateTimeField(
        null=True, blank=True,
        help_text="First time the Agora presence check found exactly ONE party "
                   "still in the channel (the other left/crashed but this side's "
                   "app kept the RTC session alive in the background); ends the "
                   "call once this has held for a confirm window."
    )
    duration_seconds = models.PositiveIntegerField(default=0)
    executive_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    ended_by = models.CharField(max_length=50, null=True, blank=True)
    end_request_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    user_joined_at = models.DateTimeField(null=True, blank=True)
    user_left_at = models.DateTimeField(null=True, blank=True)
    executive_joined_at = models.DateTimeField(null=True, blank=True)
    executive_left_at = models.DateTimeField(null=True, blank=True)
    talk_overlap_seconds = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Seconds both parties were actually present together, computed "
                   "from user/executive joined/left timestamps. Reporting only — "
                   "does not affect billing."
    )
    hangup_reason = models.CharField(
        max_length=50, null=True, blank=True,
        help_text="Why the call ended: an Agora-reported leave reason when "
                   "available, otherwise a fallback derived from ended_by "
                   "(e.g. user_ended, executive_ended, system_timeout)."
    )

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

    def mark_joined(self, party=None):
        """
        party: "user" or "executive", when known, additionally records that
        party's own join time. Reporting only — does not change joined_at's
        existing semantics or any billing behavior.
        """
        update_fields = ["joined_at", "status", "is_active"]

        if not self.joined_at:
            self.joined_at = timezone.now()
        if self.status in ["pending", "ringing"]:
            self.status = "joined"
        self.is_active = True

        if party == "user" and not self.user_joined_at:
            self.user_joined_at = timezone.now()
            update_fields.append("user_joined_at")
        elif party == "executive" and not self.executive_joined_at:
            self.executive_joined_at = timezone.now()
            update_fields.append("executive_joined_at")

        self.save(update_fields=update_fields)

    def _compute_final_duration(self, ended_at):
        base_start = self.joined_at or self.start_time
        return (ended_at - base_start) if ended_at and base_start else timezone.timedelta()

    def end_call(self, ender="client", request_id=None, effective_end_time=None):
        """
        effective_end_time: bill/log the call as if it ended at this timestamp
        instead of right now. Used by the stale-call reaper's presence checks —
        by the time a confirm window (e.g. the 32s partial-presence grace)
        elapses and this actually runs, real time has moved past the moment the
        other party genuinely left. Without this, the still-present side would
        be billed/paid for the confirm-window seconds on top of a call that was
        effectively already over.
        """
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

            now_time = effective_end_time or timezone.now()
            self.end_time = now_time

            if not self.joined_at:
                self.status = "cancelled" if ender in ["user", "client"] else "missed"
                self.duration = timedelta()
                self.duration_seconds = 0
                self.is_active = False
                self.ended_by = ender
                if not self.hangup_reason:
                    self.hangup_reason = ender
                if request_id:
                    self.end_request_id = request_id

                if hasattr(self.executive, "on_call"):
                    exec_obj = Executive.objects.select_for_update().get(id=self.executive.id)
                    exec_obj.on_call = False
                    exec_obj.save(update_fields=["on_call"])
                    self.executive.on_call = False

                self.save(update_fields=[
                    "end_time", "duration", "duration_seconds", "status", "is_active",
                    "ended_by", "hangup_reason", "end_request_id",
                    "user_joined_at", "user_left_at", "executive_joined_at", "executive_left_at",
                ])
                return

            base_start = self.joined_at
            self.duration = (now_time - base_start)
            duration_seconds = int(self.duration.total_seconds())
            self.duration_seconds = duration_seconds

            coins_to_deduct = int(Decimal(duration_seconds) * Decimal(str(self.coins_per_second)))

            if hasattr(self.user, "stats"):
                user_stats = UserStats.objects.select_for_update().get(user=self.user)
                actual_debited = min(coins_to_deduct, user_stats.coin_balance)
                self.coins_deducted = actual_debited
                user_stats.coin_balance = user_stats.coin_balance - actual_debited
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
            if not self.hangup_reason:
                self.hangup_reason = ender
            if request_id:
                self.end_request_id = request_id

            # Reporting only — the seconds both parties were actually present
            # together, distinct from duration/duration_seconds above (which
            # remain the sole basis for coins_deducted/executive_earnings).
            if self.user_joined_at and self.executive_joined_at:
                overlap_start = max(self.user_joined_at, self.executive_joined_at)
                overlap_end = min(self.user_left_at or now_time, self.executive_left_at or now_time)
                self.talk_overlap_seconds = max(0, int((overlap_end - overlap_start).total_seconds()))

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
                "hangup_reason",
                "talk_overlap_seconds",
                "end_request_id",
                "user_joined_at",
                "user_left_at",
                "executive_joined_at",
                "executive_left_at",
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
    def end_stale_ongoing_calls(stale_after_seconds=25, no_heartbeat_fallback_seconds=300,
                                 ringing_timeout_seconds=30, check_agora_presence=True,
                                 presence_grace_seconds=20, presence_confirm_seconds=10,
                                 presence_partial_confirm_seconds=32):
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

        If check_agora_presence is True and Agora RESTful credentials are
        configured, joined calls are checked directly against Agora's channel
        presence API (ground truth from Agora's own servers), distinguishing
        three states:
          - BOTH parties present: confirmed fully alive. Refreshes
            last_heartbeat, protecting the call from the no-heartbeat fallback
            below even if the app itself never sends a heartbeat ping.
          - EXACTLY ONE party present: the other side left/crashed but this
            side's app kept the RTC session alive in the background (e.g. a
            foreground service survives the task being swiped away). Not
            acted on immediately — presence_partial_confirm_seconds requires
            this lopsided state to persist across a follow-up check before
            ending the call, in case the missing side reconnects.
          - NEITHER present: presence_grace_seconds gives a just-joined call
            time to finish the RTC handshake, and presence_confirm_seconds
            requires the absence to persist across a follow-up check before
            ending the call, so one momentary blip (network handoff,
            transient Agora API hiccup) doesn't kill a call that reconnects a
            second later.
        """
        ended = []
        # Calls presence-check gave a definitive (non-None) answer for this cycle —
        # confirmed alive, or a pending/confirmed miss (full or partial). All of
        # these are authoritative decisions that must NOT be second-guessed by the
        # blunter no-heartbeat fallback query below (otherwise a call presence-check
        # is patiently waiting to confirm still gets killed by that separate timer).
        presence_evaluated = []

        if check_agora_presence:
            from calls.utils import agora_presence_configured, get_channel_active_uids

            if agora_presence_configured():
                grace_cutoff = timezone.now() - timedelta(seconds=presence_grace_seconds)
                joined_calls = AgoraCallHistory.objects.filter(
                    status="joined", joined_at__lte=grace_cutoff,
                )
                for call in joined_calls:
                    active_uids = get_channel_active_uids(call.channel_name)
                    if active_uids is None:
                        # Unknown (API error/not configured) — don't act on it, fall through to timers below.
                        continue
                    presence_evaluated.append(call.id)
                    expected_uids = {str(call.uid), str(call.callee_uid)}
                    present_count = len(expected_uids & active_uids)

                    if present_count == 2:
                        # Both confirmed alive by Agora's own servers — counts as a
                        # heartbeat, and clears any pending miss so a later blip
                        # starts counting fresh.
                        call.last_heartbeat = timezone.now()
                        call.presence_missed_since = None
                        call.presence_partial_since = None
                        call.save(update_fields=[
                            "last_heartbeat", "presence_missed_since", "presence_partial_since",
                        ])
                        continue

                    if present_count == 1:
                        # Only one side is actually still connected — the other
                        # left/crashed, but this side's app/foreground service kept
                        # the RTC session alive. Give it presence_partial_confirm_seconds
                        # in case the missing side reconnects, then end the call.
                        if call.presence_partial_since is None:
                            call.presence_partial_since = timezone.now()
                            call.save(update_fields=["presence_partial_since"])
                            continue

                        if (timezone.now() - call.presence_partial_since).total_seconds() >= presence_partial_confirm_seconds:
                            # Bill/pay up to the moment the other side was first seen
                            # missing, not up to now — otherwise the still-present side
                            # is charged/paid for the whole confirm window on top of a
                            # call that was effectively already over.
                            call.end_call(ender="agora_presence_partial",
                                           effective_end_time=call.presence_partial_since)
                            ended.append(call.id)
                        continue

                    # present_count == 0: neither party is in the channel.
                    if call.presence_missed_since is None:
                        # First time we've seen it missing — wait for confirmation, don't end yet.
                        call.presence_missed_since = timezone.now()
                        call.save(update_fields=["presence_missed_since"])
                        continue

                    if (timezone.now() - call.presence_missed_since).total_seconds() >= presence_confirm_seconds:
                        # Missing on this AND a prior check, confirm_seconds apart — genuinely gone.
                        # Same reasoning: bill up to when it was first seen missing.
                        call.end_call(ender="agora_presence_check",
                                       effective_end_time=call.presence_missed_since)
                        ended.append(call.id)

        heartbeat_cutoff = timezone.now() - timedelta(seconds=stale_after_seconds)
        fallback_cutoff = timezone.now() - timedelta(seconds=no_heartbeat_fallback_seconds)
        stale_joined_ids = AgoraCallHistory.objects.filter(
            status="joined",
        ).exclude(
            id__in=ended,
        ).exclude(
            id__in=presence_evaluated,
        ).filter(
            models.Q(last_heartbeat__isnull=False, last_heartbeat__lte=heartbeat_cutoff) |
            models.Q(last_heartbeat__isnull=True, joined_at__lte=fallback_cutoff)
        ).values_list("id", flat=True)

        for call_id in stale_joined_ids:
            call = AgoraCallHistory.objects.get(id=call_id)
            # If we have a real last-heartbeat signal, bill up to that moment
            # rather than now (same reasoning as the presence-check paths
            # above). If a heartbeat was NEVER received at all, we have no
            # confident signal of when it actually died — deliberately keep
            # billing up to now in that case, per the generous-fallback
            # rationale in this method's docstring (avoids undercharging a
            # call that may have genuinely run the whole fallback window).
            call.end_call(
                ender="system_timeout",
                effective_end_time=call.last_heartbeat,
            )
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
    