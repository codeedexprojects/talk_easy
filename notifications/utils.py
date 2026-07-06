import logging

from firebase_admin import messaging

from calls.utils import firebase_initialized

logger = logging.getLogger("notifications")

# Topics every device's FCM token is subscribed to based on account type.
TOPIC_ALL_USERS = "talkeazy_user"
TOPIC_ALL_EXECUTIVES = "talkeazy_executive"
TOPIC_ALL_MEMBERS = "talkeazy_all"
AUDIENCE_TOPICS = {
    "users": [TOPIC_ALL_USERS],
    "executives": [TOPIC_ALL_EXECUTIVES],
    "all": [TOPIC_ALL_MEMBERS],
}


def subscribe_token_to_topic(token, topic):
    """Subscribe a single device token to `topic`. Never raises."""
    if not token or not str(token).strip():
        return False

    if not firebase_initialized:
        logger.warning("[FCM] Firebase not initialized — skipping topic subscribe.")
        return False

    try:
        messaging.subscribe_to_topic([token], topic)
        return True
    except Exception as exc:
        logger.error("[FCM] Failed to subscribe token to topic %s: %s", topic, exc, exc_info=True)
        return False


def unsubscribe_token_from_topic(token, topic):
    """Unsubscribe a single device token from `topic`. Never raises."""
    if not token or not str(token).strip():
        return False

    if not firebase_initialized:
        logger.warning("[FCM] Firebase not initialized — skipping topic unsubscribe.")
        return False

    try:
        messaging.unsubscribe_from_topic([token], topic)
        return True
    except Exception as exc:
        logger.error("[FCM] Failed to unsubscribe token from topic %s: %s", topic, exc, exc_info=True)
        return False


def send_topic_fcm_notification(audience, title, body, image_url=None, data=None):
    """
    Send an FCM push notification to whichever topic(s) `audience` maps to
    ('users' -> all_users, 'executives' -> all_executives, 'all' -> both).

    Returns (success_count, failure_count) counted per topic attempted
    (e.g. 'all' can be at most 2/0) — FCM doesn't report per-device results
    for topic sends.
    Never raises — logs failures and keeps going.
    """
    topics = AUDIENCE_TOPICS.get(audience, [])

    if not topics:
        logger.warning("[FCM] Topic send skipped — unknown audience %r.", audience)
        return 0, 0

    if not firebase_initialized:
        logger.warning("[FCM] Firebase not initialized — skipping topic notification.")
        return 0, len(topics)

    safe_data = {}
    if data:
        for key, value in data.items():
            safe_data[str(key)] = str(value)

    success_count = 0
    failure_count = 0

    for topic in topics:
        message = messaging.Message(
            notification=messaging.Notification(
                title=str(title) if title else "",
                body=str(body) if body else "",
                image=image_url or None,
            ),
            data=safe_data,
            topic=topic,
        )
        try:
            messaging.send(message)
            success_count += 1
        except Exception as exc:
            logger.error("[FCM] Topic send failed for topic %s: %s", topic, exc, exc_info=True)
            failure_count += 1

    logger.info(
        "[FCM] Topic notification complete. audience=%s success=%s failure=%s",
        audience, success_count, failure_count,
    )
    return success_count, failure_count
