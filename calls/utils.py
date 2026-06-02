import time
import os
import logging
from django.conf import settings
from agora_token_builder import RtcTokenBuilder
from firebase_admin import messaging, credentials
import firebase_admin

logger = logging.getLogger("calls")


def build_agora_token(channel_name: str, uid: int, role: int = 1, ttl_seconds: int | None = None) -> str:
    app_id = settings.AGORA_APP_ID
    app_cert = settings.AGORA_APP_CERTIFICATE
    ttl = ttl_seconds or settings.AGORA_TOKEN_TTL_SECONDS if hasattr(settings, "AGORA_TOKEN_TTL_SECONDS") else 3600
    privilege_expired_ts = int(time.time()) + int(ttl)
    return RtcTokenBuilder.buildTokenWithUid(app_id, app_cert, channel_name, uid, role, privilege_expired_ts)


def generate_agora_token(channel_name, uid, role=1):
    expiration_time = int(time.time()) + settings.AGORA_TOKEN_TTL_SECONDS
    token = RtcTokenBuilder.buildTokenWithUid(
        settings.AGORA_APP_ID,
        settings.AGORA_APP_CERTIFICATE,
        channel_name,
        uid,
        role,
        expiration_time
    )
    return token


# ─────────────────────────────────────────────────────────────────────────────
# Firebase / FCM Initialization
# ─────────────────────────────────────────────────────────────────────────────
# Use an absolute path derived from BASE_DIR so this works regardless of the
# working directory at runtime (Daphne, Gunicorn, manage.py runserver, etc.)
from pathlib import Path
_BASE_DIR = Path(__file__).resolve().parent.parent   # project root

# ⚠️  IMPORTANT: Update this filename if you replace the service-account JSON.
_FIREBASE_JSON_FILENAME = "talkeasy-8420b-firebase-adminsdk-fbsvc-a8fc3da08d.json"
_FIREBASE_CREDENTIALS_PATH = _BASE_DIR / "talkeasy" / _FIREBASE_JSON_FILENAME

firebase_initialized = False

if not firebase_admin._apps:
    if _FIREBASE_CREDENTIALS_PATH.exists():
        try:
            cred = credentials.Certificate(str(_FIREBASE_CREDENTIALS_PATH))
            firebase_admin.initialize_app(cred)
            firebase_initialized = True
            logger.info("[FCM] Firebase initialized successfully. Apps: %s", list(firebase_admin._apps.keys()))
        except Exception as exc:
            logger.error("[FCM] Firebase initialization FAILED: %s", exc, exc_info=True)
            firebase_initialized = False
    else:
        logger.warning(
            "[FCM] Firebase credentials file NOT found — FCM notifications are disabled. "
            "Expected at: %s", _FIREBASE_CREDENTIALS_PATH
        )
        firebase_initialized = False
else:
    # Already initialized (e.g. multiple workers / hot-reload)
    firebase_initialized = True
    logger.info("[FCM] Firebase already initialized. Apps: %s", list(firebase_admin._apps.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# FCM Send Helper
# ─────────────────────────────────────────────────────────────────────────────

def send_fcm_notification(token, title, body, data=None):
    """
    Send an FCM push notification to a single device.

    Returns True on success, False on any failure.
    Logs the exact failure reason — never swallows exceptions silently.
    """
    if not firebase_initialized:
        logger.warning("[FCM] Firebase not initialized — skipping notification (token=%s)", token)
        return False

    if not token:
        logger.warning("[FCM] No FCM token provided — skipping notification.")
        return False

    # Clean token
    token = str(token).strip()

    # FCM data payload values MUST all be strings
    safe_data = {}
    if data:
        for key, value in data.items():
            safe_data[str(key)] = str(value)

    is_incoming_call = data and str(data.get("type", "")) == "incoming_call"

    if is_incoming_call:
        import datetime
        # Data-only message with high priority for VoIP / Background Call processing
        message = messaging.Message(
            data=safe_data,
            token=token,
            android=messaging.AndroidConfig(
                priority='high',
                ttl=datetime.timedelta(seconds=30)
            ),
            apns=messaging.APNSConfig(
                headers={
                    'apns-priority': '10',
                    'apns-expiration': '0'
                }
            )
        )
    else:
        # Standard notification message
        message = messaging.Message(
            notification=messaging.Notification(
                title=str(title) if title else "",
                body=str(body) if body else "",
            ),
            data=safe_data,
            token=token,
        )

    try:
        response = messaging.send(message)
        logger.info("[FCM] Notification sent successfully. Message ID: %s | Token: %s", response, token[:20])
        return True

    except messaging.UnregisteredError:
        logger.error("[FCM] Token is unregistered/invalid. Token: %s", token[:20])
        return False

    except messaging.InvalidArgumentError as exc:
        logger.error("[FCM] Invalid argument: %s | Token: %s", exc, token[:20])
        return False

    except Exception as exc:
        logger.error(
            "[FCM] Unexpected error sending notification: %s | Token: %s",
            exc, token[:20], exc_info=True
        )
        return False