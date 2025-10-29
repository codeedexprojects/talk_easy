import time
from django.conf import settings
from agora_token_builder import RtcTokenBuilder
from firebase_admin import messaging,credentials
import firebase_admin



def build_agora_token(channel_name: str, uid: int, role: int = 1, ttl_seconds: int | None = None) -> str:
    app_id = settings.AGORA_APP_ID
    app_cert = settings.AGORA_APP_CERTIFICATE
    ttl = ttl_seconds or settings.AGORa_TOKEN_TTL_SECONDS if hasattr(settings, "AGORA_TOKEN_TTL_SECONDS") else 3600
    privilege_expired_ts = int(time.time()) + int(ttl)
    return RtcTokenBuilder.buildTokenWithUid(app_id, app_cert, channel_name, uid, role, privilege_expired_ts)


# calls/utils.py

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



cred = credentials.Certificate("talkeasy/talkeasy-8420b-firebase-adminsdk-fbsvc-ac5f82316d.json")
firebase_admin.initialize_app(cred)

def send_fcm_notification(token, title, body, data=None):
    if not token:
        print("No FCM token provided, skipping notification.")
        return

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        token=token,
    )

    try:
        response = messaging.send(message)
        print(f"FCM Notification sent successfully: {response}")
    except Exception as e:
        print(f"Error sending FCM notification: {e}")
