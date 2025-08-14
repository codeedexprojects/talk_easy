# """
# ASGI config for talkeasy project.

# It exposes the ASGI callable as a module-level variable named ``application``.

# For more information on this file, see
# https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
# """

# import os

# from django.core.asgi import get_asgi_application

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talkeasy.settings')

# application = get_asgi_application()
# asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import users.routing  # Import your WebSocket routes

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'talk_easy.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),  # Regular HTTP requests
    "websocket": AuthMiddlewareStack(
        URLRouter(
            users.routing.websocket_urlpatterns
        )
    ),
})

