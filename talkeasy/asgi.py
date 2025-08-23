# your_project_name/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import calls.routing  # replace with your app name

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "talkeasy.settings")

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            calls.routing.websocket_urlpatterns
        )
    ),
})
