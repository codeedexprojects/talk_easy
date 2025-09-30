from django.urls import path
from .views import *

urlpatterns = [
    path("admin/login/", SuperuserLoginView.as_view(), name="super_admin_login"),
     #executive verification
    path("executives/unverified/", UnverifiedExecutivesListView.as_view(), name="unverified-executives"),
    path("executives/verify/<int:id>/", VerifyExecutiveView.as_view(), name="verify-executive"),
    #admin sessions---------------------------
    path('sessions/superusers/', SuperuserSessionsListView.as_view(), name='superuser-sessions-list'),
    path('sessions/my-sessions/', MyActiveSessionsView.as_view(), name='my-active-sessions'),
    path('sessions/<int:session_id>/revoke/', RevokeSessionView.as_view(), name='revoke-session'),
    path('sessions/revoke-all-others/', RevokeAllOtherSessionsView.as_view(), name='revoke-all-other-sessions'),

]
