from django.core.management.base import BaseCommand

from executives.models import Executive
from notifications.utils import (
    TOPIC_ALL_EXECUTIVES,
    TOPIC_ALL_MEMBERS,
    TOPIC_ALL_USERS,
    subscribe_token_to_topic,
)
from users.models import UserProfile


class Command(BaseCommand):
    help = (
        "One-off backfill: subscribes every stored fcm_token (from "
        "UserProfile and Executive rows saved before topic-based push "
        "notifications were introduced) to the all_users / all_executives "
        "FCM topics. Run once after deploying the topic-subscription change "
        "so already-logged-in devices start receiving admin broadcasts "
        "without waiting for their next login.\n\n"
        "Safe to re-run — subscribing an already-subscribed token is a no-op."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many tokens would be subscribed without calling Firebase.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        user_tokens = list(
            UserProfile.objects.exclude(fcm_token__isnull=True)
            .exclude(fcm_token="")
            .values_list("fcm_token", flat=True)
        )
        executive_tokens = list(
            Executive.objects.exclude(fcm_token__isnull=True)
            .exclude(fcm_token="")
            .values_list("fcm_token", flat=True)
        )

        self.stdout.write(
            f"Found {len(user_tokens)} user token(s) and "
            f"{len(executive_tokens)} executive token(s) to subscribe."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no Firebase calls made."))
            return

        self._subscribe_all(user_tokens, TOPIC_ALL_USERS, "user")
        self._subscribe_all(executive_tokens, TOPIC_ALL_EXECUTIVES, "executive")
        self._subscribe_all(user_tokens, TOPIC_ALL_MEMBERS, "user (all-members)")
        self._subscribe_all(executive_tokens, TOPIC_ALL_MEMBERS, "executive (all-members)")

    def _subscribe_all(self, tokens, topic, label):
        success = 0
        failure = 0
        for token in tokens:
            if subscribe_token_to_topic(token, topic):
                success += 1
            else:
                failure += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: subscribed {success}/{len(tokens)} token(s) to {topic} "
                f"({failure} failed — see logs)"
            )
        )
