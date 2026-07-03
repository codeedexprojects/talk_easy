from django.core.management.base import BaseCommand
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from calls.models import AgoraCallHistory


class Command(BaseCommand):
    help = (
        "Force-end calls stuck in 'joined' status whose heartbeat has gone "
        "stale (e.g. the app crashed or lost network mid-call), so the call "
        "row and the executive's on_call flag don't stay stuck forever. "
        "Intended to be run periodically (e.g. every minute via cron/Task Scheduler)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-after",
            type=int,
            default=90,
            help="Seconds since last heartbeat/join before a call is considered dead (default: 90)",
        )

    def handle(self, *args, **options):
        stale_after = options["stale_after"]
        ended = AgoraCallHistory.end_stale_ongoing_calls(stale_after_seconds=stale_after)

        for call_id in ended:
            try:
                call = AgoraCallHistory.objects.select_related("user", "executive").get(id=call_id)
            except AgoraCallHistory.DoesNotExist:
                continue
            self._notify(call)

        if ended:
            self.stdout.write(self.style.SUCCESS(f"Ended {len(ended)} stale call(s): {list(ended)}"))
        else:
            self.stdout.write("No stale calls found.")

    def _notify(self, call):
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return
            for group_name in [f"user_client_{call.user_id}", f"user_executive_{call.executive_id}"]:
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        "type": "call_ended",
                        "call_id": call.id,
                        "reason": "Call ended automatically due to connection loss",
                        "ended_by": call.ended_by,
                        "coins_deducted": call.coins_deducted,
                        "executive_earnings": float(call.executive_earnings),
                        "duration_seconds": call.duration_seconds,
                    },
                )
        except Exception as exc:
            self.stderr.write(f"Failed to notify for call {call.id}: {exc}")
