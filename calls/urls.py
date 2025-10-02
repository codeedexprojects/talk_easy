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
    path("user-call/<int:call_id>/reject/", RejectCallViewUser.as_view(), name="reject-call-user"),
    path("Executive-call/<int:call_id>/reject/", RejectCallViewExecutive.as_view(), name="reject-call-executive"),

    #ratings
    path('all-ratings/', CallRatingListAPIView.as_view(), name='all-ratings'),
    path('create-rating/<int:user_id>/<int:executive_id>/', CreateCallRatingAPIView.as_view(), name='create-rating'),
    path('executive-ratings/<int:executive_id>/', ExecutiveRatingsAPIView.as_view(), name='executive-ratings'),
    path('user-ratings/<int:user_id>/', UserRatingsAPIView.as_view(), name='user-ratings'),
    path('executive-average-ratings/<int:executive_id>/', ExecutiveAverageRatingAPIView.as_view(), name='executive-avg-rating'),
    #call history
    path("call-History/", CallHistoryListAPIView.as_view(), name="call-history-list"), #admin list
    path("user-history/", UserCallHistoryAPIView.as_view(), name="user-call-history"), #user list
    path("executive-call-history/", ExecutiveCallHistoryListAPIView.as_view(), name="executive-call-history"), #executive list
    path("executives-recent-calls/<int:executive_id>/", RecentExecutiveCallsAPIView.as_view(), name="recent-calls-executive"),

]
