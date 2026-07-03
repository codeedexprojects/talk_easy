import logging

from firebase_admin import messaging

from calls.utils import firebase_initialized

logger = logging.getLogger("notifications")

# FCM limit for a single multicast call.
_BATCH_SIZE = 500


def send_bulk_fcm_notification(tokens, title, body, image_url=None, data=None):
    """
    Send an FCM push notification to many devices at once.

    Returns (success_count, failure_count).
    Invalid/duplicate/blank tokens are skipped before sending.
    Never raises — logs failures and keeps going.
    """
    tokens = sorted({str(t).strip() for t in tokens if t and str(t).strip()})

    if not tokens:
        logger.warning("[FCM] Bulk send skipped — no valid tokens.")
        return 0, 0

    if not firebase_initialized:
        logger.warning("[FCM] Firebase not initialized — skipping bulk notification.")
        return 0, len(tokens)

    safe_data = {}
    if data:
        for key, value in data.items():
            safe_data[str(key)] = str(value)

    success_count = 0
    failure_count = 0

    for i in range(0, len(tokens), _BATCH_SIZE):
        batch = tokens[i:i + _BATCH_SIZE]
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=str(title) if title else "",
                body=str(body) if body else "",
                image=image_url or None,
            ),
            data=safe_data,
            tokens=batch,
        )
        try:
            response = messaging.send_each_for_multicast(message)
            success_count += response.success_count
            failure_count += response.failure_count
            for token, send_response in zip(batch, response.responses):
                if not send_response.success:
                    logger.error(
                        "[FCM] Bulk send failed for token %s: %s",
                        token[:20], send_response.exception,
                    )
        except Exception as exc:
            logger.error("[FCM] Bulk send batch failed: %s", exc, exc_info=True)
            failure_count += len(batch)

    logger.info(
        "[FCM] Bulk notification complete. success=%s failure=%s", success_count, failure_count
    )
    return success_count, failure_count
