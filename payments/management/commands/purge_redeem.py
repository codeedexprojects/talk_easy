from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from payments.models import ExecutivePayoutRedeem
from executives.models import ExecutiveStats


class Command(BaseCommand):
    help = (
        "Completely remove an ExecutivePayoutRedeem row. If the redeem is "
        "still 'pending', refunds the redemption amount back to the "
        "executive's pending_payout (it was deducted when the redeem was "
        "created). If the redeem is 'approved'/'paid'/'rejected', no "
        "pending_payout reversal is applied by default since it was already "
        "settled (rejected requests are refunded on rejection elsewhere); "
        "use --force-refund to also refund those.\n\n"
        "Run with --dry-run first to see exactly what would change."
    )

    def add_arguments(self, parser):
        parser.add_argument("redeem_id", type=int, help="ExecutivePayoutRedeem id to purge")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be reversed/deleted without changing anything.",
        )
        parser.add_argument(
            "--force-refund",
            action="store_true",
            help="Refund pending_payout even if the redeem isn't 'pending'.",
        )

    def handle(self, *args, **options):
        redeem_id = options["redeem_id"]
        dry_run = options["dry_run"]
        force_refund = options["force_refund"]

        with transaction.atomic():
            try:
                redeem = ExecutivePayoutRedeem.objects.select_for_update().select_related(
                    "executive", "redemption_option"
                ).get(id=redeem_id)
            except ExecutivePayoutRedeem.DoesNotExist:
                raise CommandError(f"ExecutivePayoutRedeem {redeem_id} does not exist")

            amount = redeem.approved_amount or redeem.redemption_option.amount

            self.stdout.write(
                f"Redeem {redeem.id}: executive={redeem.executive_id} "
                f"({redeem.executive.name}) amount={amount} "
                f"status={redeem.status} upi={redeem.upi_details} "
                f"account_number={redeem.account_number} "
                f"requested_at={redeem.requested_at} "
                f"processed_at={redeem.processed_at}"
            )

            should_refund = redeem.status == "pending" or force_refund

            if dry_run:
                if should_refund:
                    self.stdout.write(
                        f"Would refund {amount} to executive {redeem.executive_id}'s pending_payout."
                    )
                else:
                    self.stdout.write(
                        "Would NOT refund pending_payout (status is "
                        f"'{redeem.status}'; pass --force-refund to override)."
                    )
                self.stdout.write(self.style.WARNING("Dry run — no changes made."))
                transaction.set_rollback(True)
                return

            if should_refund and hasattr(redeem.executive, "stats"):
                exec_stats = ExecutiveStats.objects.select_for_update().get(
                    executive=redeem.executive
                )
                exec_stats.pending_payout = exec_stats.pending_payout + Decimal(amount)
                exec_stats.save(update_fields=["pending_payout"])
                self.stdout.write(
                    f"Refunded {amount} to executive {redeem.executive_id}'s "
                    f"pending_payout (new balance: {exec_stats.pending_payout})"
                )

            redeem.delete()
            self.stdout.write(
                self.style.SUCCESS(f"Deleted redeem {redeem_id}.")
            )
