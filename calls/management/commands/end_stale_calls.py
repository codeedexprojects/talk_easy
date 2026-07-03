import time

from django.core.management.base import BaseCommand
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from calls.models import AgoraCallHistory

MAX_CONSECUTIVE_FAILURES = 5


class Command(BaseCommand):
    help = (
        "Force-end calls stuck in 'joined'/'ringing'/'pending' status that "
        "have gone stale (e.g. the app crashed or lost network mid-call), so "
        "the call row and the executive's on_call flag don't stay stuck "
        "forever. Relies on the client sending periodic {'type':'heartbeat', "
        "'call_id':...} pings while joined (every ~5-8s recommended) to keep "
        "last_heartbeat fresh, and/or the Agora channel presence API (ground "
        "truth) if AGORA_CUSTOMER_ID/SECRET are configured.\n\n"
        "Run with --loop for continuous polling within a single long-lived "
        "process (e.g. under PM2) — this avoids paying Django's startup cost "
        "on every cycle, unlike re-invoking this command from cron/a shell "
        "loop every few seconds. After 5 consecutive failed cycles, the "
        "process exits non-zero so the process manager's restart/alerting "
        "surfaces the problem instead of retrying a broken run forever."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--stale-after",
            type=int,
            default=25,
            help="Seconds since last heartbeat before a joined call is considered dead, "
                 "when heartbeats ARE being received (default: 25)",
        )
        parser.add_argument(
            "--no-heartbeat-fallback",
            type=int,
            default=300,
            help="Seconds since joined_at before a joined call with NO heartbeat ever "
                 "recorded is considered dead. Keep generous until the client sends "
                 "heartbeats, since duration/coin billing is computed from joined_at "
                 "(default: 300)",
        )
        parser.add_argument(
            "--ringing-timeout",
            type=int,
            default=30,
            help="Seconds before an unanswered ringing/pending call is marked missed (default: 30)",
        )
        parser.add_argument(
            "--no-agora-check",
            action="store_true",
            help="Skip the Agora channel presence check (ground-truth, requires "
                 "AGORA_CUSTOMER_ID/SECRET) and rely only on heartbeat/timeout logic.",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Run continuously in this process instead of exiting after one pass.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=5,
            help="Seconds to sleep between passes when --loop is set (default: 5).",
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self._run_loop(options)
        else:
            self._run_once(options)

    def _run_loop(self, options):
        interval = options["interval"]
        self.stdout.write(f"[end_stale_calls] loop starting, interval={interval}s")
        consecutive_failures = 0

        while True:
            try:
                self._run_once(options)
                consecutive_failures = 0
            except Exception as exc:
                consecutive_failures += 1
                self.stderr.write(
                    f"[end_stale_calls] cycle failed ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {exc}"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    self.stderr.write(
                        "[end_stale_calls] too many consecutive failures, exiting "
                        "so the process manager can restart/alert instead of "
                        "retrying a broken run forever."
                    )
                    raise SystemExit(1)

            time.sleep(interval)

    def _run_once(self, options):
        stale_after = options["stale_after"]
        no_heartbeat_fallback = options["no_heartbeat_fallback"]
        ringing_timeout = options["ringing_timeout"]
        ended = AgoraCallHistory.end_stale_ongoing_calls(
            stale_after_seconds=stale_after,
            no_heartbeat_fallback_seconds=no_heartbeat_fallback,
            ringing_timeout_seconds=ringing_timeout,
            check_agora_presence=not options["no_agora_check"],
        )

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
            groups = [f"user_{call.user_id}", f"executive_{call.executive.executive_id}"]
            if call.status == "missed":
                event = {"type": "call_missed", "call_id": call.id}
            else:
                event = {
                    "type": "call_ended",
                    "call_id": call.id,
                    "reason": "Call ended automatically due to connection loss",
                    "ended_by": call.ended_by,
                    "coins_deducted": call.coins_deducted,
                    "executive_earnings": float(call.executive_earnings),
                    "duration_seconds": call.duration_seconds,
                }
            for group_name in groups:
                async_to_sync(channel_layer.group_send)(group_name, event)
        except Exception as exc:
            self.stderr.write(f"Failed to notify for call {call.id}: {exc}")
