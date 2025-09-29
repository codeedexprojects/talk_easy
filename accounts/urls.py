from django.urls import path
from .views import *

urlpatterns = [
    path("admin/login/", SuperuserLoginView.as_view(), name="super_admin_login"),

    # Session management API endpoints -----------------------------------------
    path('admin/sessions/logout-others/',LogoutAllSessionsAPIView.as_view(),name='admin_logout_all_sessions_api'),
    path('admin/sessions/logout-all/',LogoutAllAndCurrentAPIView.as_view(),name='admin_logout_all_and_current_api'),
    path('admin/sessions/active/',ActiveSessionsAPIView.as_view(),name='admin_active_sessions_api'),    
    path('admin/sessions/terminate/<str:session_key>/',TerminateSpecificSessionAPIView.as_view(),name='admin_terminate_session_api'),
     #executive verification
    path("executives/unverified/", UnverifiedExecutivesListView.as_view(), name="unverified-executives"),
    path("executives/verify/<int:id>/", VerifyExecutiveView.as_view(), name="verify-executive"),
    
    path('sessions/superusers/', SuperuserSessionsListView.as_view(), name='superuser-sessions-list'),
    path('sessions/my-sessions/', MyActiveSessionsView.as_view(), name='my-active-sessions'),
    path('sessions/<int:session_id>/revoke/', RevokeSessionView.as_view(), name='revoke-session'),
    path('sessions/revoke-all-others/', RevokeAllOtherSessionsView.as_view(), name='revoke-all-other-sessions'),

]
