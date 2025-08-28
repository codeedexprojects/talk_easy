# calls/urls.py
from django.urls import path
from calls.views import *

urlpatterns = [
    path("initiate/", CallInitiateView.as_view(), name="initiate-call"),
    path("calls/<int:call_id>/join/", CallJoinView.as_view(), name="call-join"),
    path("calls/<str:channel_name>/", GetCallByChannelView.as_view(), name="call-detail"),
    path("calls/<str:channel_name>/joined/", MarkJoinedView.as_view(), name="call-joined"),
    path("end-call/<int:call_id>/", EndCallView.as_view(), name="end-call"),
    path("agora/webhook/", AgoraWebhookView.as_view(), name="agora-webhook"),
    path("calls/<int:call_id>/end/", EndCallView.as_view(), name="end-call"),
    path("calls/<int:call_id>/reject/", RejectCallView.as_view(), name="reject-call"),
    #ratings
    path('all-ratings/', CallRatingListAPIView.as_view(), name='all-ratings'),
    path('create-rating/<int:user_id>/<int:executive_id>/', CreateCallRatingAPIView.as_view(), name='create-rating'),
    path('executive-ratings/<int:executive_id>/', ExecutiveRatingsAPIView.as_view(), name='executive-ratings'),
    path('user-ratings/<int:user_id>/', UserRatingsAPIView.as_view(), name='user-ratings'),
    path('executive-average-ratings/<int:executive_id>/', ExecutiveAverageRatingAPIView.as_view(), name='executive-avg-rating'),

]
