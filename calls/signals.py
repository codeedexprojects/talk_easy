from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils.timezone import now
from datetime import timedelta
from .models import AgoraCallHistory
from users.models import UserStats
from executives.models import ExecutiveStats


@receiver(pre_save, sender=AgoraCallHistory)
def detect_status_transition(sender, instance, **kwargs):
    """
    Capture previous status before saving to detect transitions.
    """
    if not instance.pk:
        instance._previous_status = None
    else:
        try:
            old_instance = AgoraCallHistory.objects.get(pk=instance.pk)
            instance._previous_status = old_instance.status
        except AgoraCallHistory.DoesNotExist:
            instance._previous_status = None


@receiver(post_save, sender=AgoraCallHistory)
def update_stats_on_call_update(sender, instance, created, **kwargs):
    """
    Updates UserStats and ExecutiveStats when call status changes.
    total_picked_calls increments only when the call ENDS.
    """
    try:
        prev_status = getattr(instance, "_previous_status", None)

        # ---------------------------------------------
        # USER SIDE
        # ---------------------------------------------
        if not created and instance.status == "ended" and prev_status != "ended":
            user_stats, _ = UserStats.objects.get_or_create(user=instance.user)

            # Calculate duration
            if instance.start_time and instance.end_time:
                duration_seconds = int((instance.end_time - instance.start_time).total_seconds())
                instance.duration_seconds = duration_seconds
                instance.duration = timedelta(seconds=duration_seconds)
                instance.save(update_fields=["duration", "duration_seconds"])

                # Update user totals
                user_stats.total_calls += 1
                user_stats.total_call_seconds += duration_seconds
                if instance.end_time.date() == now().date():
                    user_stats.total_call_seconds_today += duration_seconds
                user_stats.save()

        # ---------------------------------------------
        # EXECUTIVE SIDE
        # ---------------------------------------------
        exec_stats, _ = ExecutiveStats.objects.get_or_create(executive=instance.executive)

        # ✅ Missed calls (increment immediately)
        if not created and instance.status == "missed" and prev_status != "missed":
            exec_stats.total_missed_calls += 1
            exec_stats.save(update_fields=["total_missed_calls", "last_updated"])

        # ✅ Ended calls (count as picked + update duration + earnings)
        if not created and instance.status == "ended" and prev_status != "ended":
            # Count it as a picked (completed) call
            exec_stats.total_picked_calls += 1

            if instance.start_time and instance.end_time:
                duration_seconds = int((instance.end_time - instance.start_time).total_seconds())

                # Update talk seconds
                exec_stats.total_talk_seconds += duration_seconds  # all-time talk seconds
                exec_stats.total_talk_seconds_today += duration_seconds

                # Update on-duty seconds only if executive is online
                if getattr(instance.executive, "is_online", False):
                    exec_stats.total_on_duty_seconds += duration_seconds

                # Compute earnings
                earnings = (duration_seconds * instance.coins_per_second / 60) * float(instance.amount_per_min)
                exec_stats.total_earnings += earnings

                if instance.end_time.date() == now().date():
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
                "pending_payout",
                "last_updated",
            ])

    except Exception as e:
        print(f"Error updating stats: {e}")
