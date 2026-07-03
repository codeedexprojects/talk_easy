from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from calls.models import AgoraCallHistory
from users.models import UserStats
from executives.models import ExecutiveStats


class Command(BaseCommand):
    help = (
        "Completely remove a bad/stuck AgoraCallHistory row: refunds the "
        "coins it deducted from the user, reverses the earnings/duration "
        "it credited to the executive, then deletes the call row (and any "
        "linked CallRating via cascade). Use for calls that were left "
        "running/stuck and billed incorrectly (e.g. a stale call that ran "
        "for hours before being force-ended).\n\n"
        "Run with --dry-run first to see exactly what would change."
    )

    def add_arguments(self, parser):
        parser.add_argument("call_id", type=int, help="AgoraCallHistory id to purge")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be reversed/deleted without changing anything.",
        )

    def handle(self, *args, **options):
        call_id = options["call_id"]
        dry_run = options["dry_run"]

        with transaction.atomic():
            try:
                call = AgoraCallHistory.objects.select_for_update().select_related(
                    "user", "executive"
                ).get(id=call_id)
            except AgoraCallHistory.DoesNotExist:
                raise CommandError(f"AgoraCallHistory {call_id} does not exist")

            coins_to_refund = call.coins_deducted
            earnings_to_remove = call.executive_earnings or Decimal("0.00")
            duration_seconds = call.duration_seconds or 0

            self.stdout.write(
                f"Call {call.id} ({call.channel_name}): status={call.status} "
                f"user={call.user_id} executive={call.executive_id} "
                f"coins_deducted={coins_to_refund} "
                f"executive_earnings={earnings_to_remove} "
                f"duration_seconds={duration_seconds}"
            )

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run — no changes made."))
                transaction.set_rollback(True)
                return

            if coins_to_refund and hasattr(call.user, "stats"):
                user_stats = UserStats.objects.select_for_update().get(user=call.user)
                user_stats.coin_balance = user_stats.coin_balance + coins_to_refund
                user_stats.total_calls = max(0, user_stats.total_calls - 1)
                user_stats.total_call_seconds = max(
                    0, user_stats.total_call_seconds - duration_seconds
                )
                if call.end_time and user_stats.last_updated.date() == call.end_time.date():
                    user_stats.total_call_seconds_today = max(
                        0, user_stats.total_call_seconds_today - duration_seconds
                    )
                user_stats.save(update_fields=[
                    "coin_balance",
                    "total_calls",
                    "total_call_seconds",
                    "total_call_seconds_today",
                ])
                self.stdout.write(
                    f"Refunded {coins_to_refund} coins to user {call.user_id} "
                    f"(new balance: {user_stats.coin_balance})"
                )

            if hasattr(call.executive, "stats"):
                exec_stats = ExecutiveStats.objects.select_for_update().get(
                    executive=call.executive
                )
                exec_stats.total_picked_calls = max(0, exec_stats.total_picked_calls - 1)
                exec_stats.total_talk_seconds = max(
                    0, exec_stats.total_talk_seconds - duration_seconds
                )
                exec_stats.total_on_duty_seconds = max(
                    0, exec_stats.total_on_duty_seconds - duration_seconds
                )
                exec_stats.total_earnings = max(
                    Decimal("0.00"), exec_stats.total_earnings - earnings_to_remove
                )
                exec_stats.vault_Balance = max(
                    0, exec_stats.vault_Balance - int(earnings_to_remove)
                )
                exec_stats.pending_payout = max(
                    Decimal("0.00"), exec_stats.pending_payout - earnings_to_remove
                )
                if call.end_time and exec_stats.last_updated.date() == call.end_time.date():
                    exec_stats.total_talk_seconds_today = max(
                        0, exec_stats.total_talk_seconds_today - duration_seconds
                    )
                    exec_stats.earnings_today = max(
                        Decimal("0.00"), exec_stats.earnings_today - earnings_to_remove
                    )
                exec_stats.save(update_fields=[
                    "total_picked_calls",
                    "total_talk_seconds",
                    "total_talk_seconds_today",
                    "total_on_duty_seconds",
                    "total_earnings",
                    "earnings_today",
                    "vault_Balance",
                    "pending_payout",
                ])
                self.stdout.write(
                    f"Removed {earnings_to_remove} earnings / {duration_seconds}s "
                    f"from executive {call.executive_id}"
                )

            ratings_count = call.ratings.count()
            call.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted call {call_id} (and {ratings_count} linked rating(s))."
                )
            )
