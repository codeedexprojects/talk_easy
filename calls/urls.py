# calls/urls.py
from django.urls import path
from calls.views import *

urlpatterns = [
    path("initiate/", CallInitiateView.as_view(), name="initiate-call"),
    path("calls/<int:call_id>/join/", CallJoinView.as_view(), name="call-join"),
    path("calls/<str:channel_name>/", GetCallByChannelView.as_view(), name="call-detail"),
    path("calls/<str:channel_name>/joined/", MarkJoinedView.as_view(), name="call-joined"),
    path("end-call/", EndCallView.as_view(), name="end-call"),
    path("agora/webhook/", AgoraWebhookView.as_view(), name="agora-webhook"),
    path("calls/<int:call_id>/end/", EndCallView.as_view(), name="end-call"),
    path("calls/<int:call_id>/reject/", RejectCallView.as_view(), name="reject-call"),

]
