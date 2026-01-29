import time
import os
from django.conf import settings
from agora_token_builder import RtcTokenBuilder
from firebase_admin import messaging, credentials
import firebase_admin



def build_agora_token(channel_name: str, uid: int, role: int = 1, ttl_seconds: int | None = None) -> str:
    app_id = settings.AGORA_APP_ID
    app_cert = settings.AGORA_APP_CERTIFICATE
    ttl = ttl_seconds or settings.AGORA_TOKEN_TTL_SECONDS if hasattr(settings, "AGORA_TOKEN_TTL_SECONDS") else 3600
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



# Initialize Firebase only if credentials file exists
# This allows the project to run without Firebase configured
firebase_credentials_path = "talkeasy/talkeasy-8420b-firebase-adminsdk-fbsvc-ac5f82316d.json"
firebase_initialized = False

if os.path.exists(firebase_credentials_path):
    try:
        cred = credentials.Certificate(firebase_credentials_path)
        firebase_admin.initialize_app(cred)
        firebase_initialized = True
        print("✓ Firebase initialized successfully")
    except Exception as e:
        print(f"✗ Firebase initialization failed: {e}")
        firebase_initialized = False
else:
    print("ℹ Firebase credentials not found. FCM notifications will be disabled.")
    print(f"  Expected file: {firebase_credentials_path}")
    firebase_initialized = False

def send_fcm_notification(token, title, body, data=None):
    if not firebase_initialized:
        print("ℹ Firebase not initialized, skipping notification")
        return False
        
    if not token:
        print("No FCM token provided, skipping notification.")
        return False
    
    # Ensure token is clean string
    token = str(token).strip()
    
    # Convert all data to strings (CRITICAL!)
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
        token=token,
    )
    
    try:
        response = messaging.send(message)
        print(f"✓ FCM sent successfully: {response}")
        return True
    except messaging.UnregisteredError:
        print(f"✗ FCM token unregistered/invalid")
        return False
    except messaging.InvalidArgumentError as e:
        print(f"✗ Invalid FCM argument: {e}")
        return False
    except Exception as e:
        print(f"✗ FCM error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False