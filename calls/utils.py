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
    """
    Returns: (success: bool, error_message: str or None)
    """
    if not token:
        error_msg = "No FCM token provided"
        print(error_msg)
        return False, error_msg
    
    # Force all data to strings (CRITICAL!)
    safe_data = {}
    if data:
        for key, value in data.items():
            safe_data[str(key)] = str(value)
    
    message = messaging.Message(
        notification=messaging.Notification(
            title=str(title), 
            body=str(body)
        ),
        data=safe_data,
        token=str(token).strip(),
    )
    
    try:
        response = messaging.send(message)
        print(f"✓ FCM Notification sent successfully: {response}")
        return True, None
    except messaging.UnregisteredError as e:
        error_msg = f"FCM token unregistered: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except messaging.InvalidArgumentError as e:
        error_msg = f"Invalid FCM argument: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"❌ Error sending FCM notification: {error_msg}")
        import traceback
        traceback.print_exc()
        return False, error_msg