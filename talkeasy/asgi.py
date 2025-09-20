import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')

# 👇 settings are configured here
django_asgi_app = get_asgi_application()

# Now safe to import JWTAuthMiddleware
from calls.routing import websocket_urlpatterns
from .middleware import JWTAuthMiddleware  # import AFTER settings configured

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddleware(
        URLRouter(websocket_urlpatterns)
    ),
})