# routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns  = [
    path('ws/executive/<str:executive_id>/', consumers.ExecutivesConsumer.as_asgi()),
    path('ws/executive/', consumers.ExecutivesConsumer.as_asgi()),
    path('ws/users/', consumers.UsersConsumer.as_asgi()),
]