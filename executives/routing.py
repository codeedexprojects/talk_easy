# executives/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/executives/', consumers.ExecutivesConsumer.as_asgi()),
    path('ws/executives/<int:executive_id>/', consumers.ExecutivesConsumer.as_asgi()),
    path('ws/users/', consumers.UsersConsumer.as_asgi()),
]