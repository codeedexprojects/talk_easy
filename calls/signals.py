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
        # User completed call logic is handled securely in AgoraCallHistory.end_call() now.

        # ---------------------------------------------
        # EXECUTIVE SIDE
        # ---------------------------------------------
        exec_stats, _ = ExecutiveStats.objects.get_or_create(executive=instance.executive)

        # ✅ Missed calls (increment immediately)
        if not created and instance.status == "missed" and prev_status != "missed":
            exec_stats.total_missed_calls += 1
            exec_stats.save(update_fields=["total_missed_calls", "last_updated"])


    except Exception as e:
        print(f"Error updating stats: {e}")
