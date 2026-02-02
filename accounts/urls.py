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
    path('create-manager/', ManagerExecutiveCreateView.as_view(), name='create-manager-executive'),
    path('login-manager/', ManagerExecutiveLoginView.as_view(), name='login-manager-executive'),
    path('admin/<int:pk>/permissions/', UpdateAdminPermissionsView.as_view(), name='update-admin-permissions'),
    path('manager-executives/<int:pk>/delete/', ManagerExecutiveDeleteView.as_view(), name='delete-manager-executive'),
    path('create-manager-user/', ManagerUserCreateView.as_view(), name='create-manager-user'),
    path('login-manager-user/', ManagerUserLoginView.as_view(), name='login-manager-user'),
    path('manager-users/<int:pk>/delete/', ManagerUserDeleteView.as_view(), name='delete-manager-user'),
    path('managers/', ManagerListView.as_view(), name='manager-list'),
    path('admin/reset-password/', AdminPasswordResetView.as_view(), name='admin-reset-password'),
    path('admin-update/', AdminUpdateView.as_view(), name='admin-self-update'),           
    path('admin/update/<int:pk>/', AdminUpdateView.as_view(), name='admin-update-by-id'),  
]










