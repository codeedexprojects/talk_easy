import os
import django
from django.core.asgi import get_asgi_application

# Must be set first
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "talkeasy.settings")

# Initialize Django before importing other modules
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter
from executives.routing import websocket_urlpatterns
from executives.middleware import JWTAuthMiddleware

# Get Django ASGI application
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})