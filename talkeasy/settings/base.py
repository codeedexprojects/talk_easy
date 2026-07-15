"""
Django settings for talkeasy project - BASE CONFIGURATION

This module contains common settings shared across all environments.
Environment-specific settings are in development.py and production.py
"""

from pathlib import Path
import os
from decouple import config, Csv
from datetime import timedelta

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('DJANGO_SECRET_KEY')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework_simplejwt.token_blacklist',
    'users',
    'corsheaders',
    'accounts',
    'executives',
    'channels',
    'calls',
    'payments',
    'notifications',
    'rest_framework',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.JWTSessionTrackingMiddleware',
]

ROOT_URLCONF = 'talkeasy.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ASGI application for WebSockets
ASGI_APPLICATION = 'talkeasy.asgi.application'

# Channel Layers - using InMemoryChannelLayer for development
# Override in production.py for RabbitMQ
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

# # Database
# DATABASES = {
#     'default': {
#         'ENGINE': config('DB_ENGINE', default='django.db.backends.mysql'),
#         'NAME': config('DB_NAME'),
#         'USER': config('DB_USER'),
#         'PASSWORD': config('DB_PASSWORD'),
#         'HOST': config('DB_HOST'),
#         'PORT': config('DB_PORT', default='3306'),
#         'OPTIONS': {
#             'charset': 'utf8mb4',
#             'use_unicode': True,
#         },
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.Admin'

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'users.authentication.UserProfileJWTAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'EXCEPTION_HANDLER': 'executives.authentication.custom_exception_handler',
}

# JWT Configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=config('JWT_ACCESS_TOKEN_LIFETIME_DAYS', default=1, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'ALGORITHM': 'HS256',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id'
}

# Agora Configuration
AGORA_APP_ID = config('AGORA_APP_ID')
AGORA_APP_CERTIFICATE = config('AGORA_APP_CERTIFICATE')
AGORA_TOKEN_TTL_SECONDS = config('AGORA_TOKEN_TTL_SECONDS', default=3600, cast=int)

# Agora RESTful API credentials (Customer ID/Secret from the Agora Console —
# separate from APP_ID/APP_CERTIFICATE above). Used to query live channel
# presence for stale-call detection. Optional: leave unset to disable.
AGORA_CUSTOMER_ID = config('AGORA_CUSTOMER_ID', default=None)
AGORA_CUSTOMER_SECRET = config('AGORA_CUSTOMER_SECRET', default=None)

# Agora Notifications (channel event webhooks) — the "Secret" shown in
# Agora Console under Project > Notifications, used to verify the
# Agora-Signature-V2 (HMAC-SHA256) header on incoming webhook callbacks.
# Optional: leave unset to disable verification (NOT recommended in production).
AGORA_WEBHOOK_SECRET = config('AGORA_WEBHOOK_SECRET', default=None)

# Payment Configuration
RAZORPAY_KEY_ID = config('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = config('RAZORPAY_KEY_SECRET')
RAZORPAY_WEBHOOK_SECRET = config('RAZORPAY_WEBHOOK_SECRET', default='')

# External Services
TWO_FACTOR_API_KEY = config('TWO_FACTOR_API_KEY')

# Business Logic Configuration
COINS_PER_SECOND = config('COINS_PER_SECOND', default=3, cast=int)

# Email Configuration
# Use smtp.EmailBackend in production, console.EmailBackend for dev
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='TalkEasy Admin <noreply@talkeasy.com>')

# OTP Configuration
OTP_EXPIRY_SECONDS = 300          # 5 minutes
OTP_MAX_ATTEMPTS = 5              # Max wrong attempts before OTP is invalidated
OTP_VERIFIED_WINDOW_SECONDS = 600 # 10 min window to use verified OTP for password reset
