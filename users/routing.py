from django.urls import path
from users.consumers import ExecutiveConsumer

websocket_urlpatterns = [
    path('ws/executives/', ExecutiveConsumer.as_asgi()),
]
