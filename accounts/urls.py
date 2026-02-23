from django.urls import path
from .views import *

urlpatterns = [

    # ── Authentication ──────────────────────────────────────────────────────────
    path("admin/login/", SuperuserLoginView.as_view(), name="super_admin_login"),

    # ── Admin Profile (JWT protected) ───────────────────────────────────────────
    path('admin-profile/', AdminProfileView.as_view(), name='admin-profile'),

    # ── Phone OTP Password Reset Flow (3 steps) ─────────────────────────────────
    path('admin/password-reset/send-otp/', AdminSendOTPView.as_view(), name='admin-password-reset-send-otp'),
    path('admin/password-reset/verify-otp/', AdminVerifyOTPView.as_view(), name='admin-password-reset-verify-otp'),
    path('admin/password-reset/reset/', AdminPasswordResetView.as_view(), name='admin-password-reset-reset'),


    # ── Executive Verification ──────────────────────────────────────────────────
    path("executives/unverified/", UnverifiedExecutivesListView.as_view(), name="unverified-executives"),
    path("executives/verify/<int:id>/", VerifyExecutiveView.as_view(), name="verify-executive"),

    # ── Session Management ──────────────────────────────────────────────────────
    path('sessions/superusers/', SuperuserSessionsListView.as_view(), name='superuser-sessions-list'),
    path('sessions/my-sessions/', MyActiveSessionsView.as_view(), name='my-active-sessions'),
    path('sessions/<int:session_id>/revoke/', RevokeSessionView.as_view(), name='revoke-session'),
    path('sessions/revoke-all-others/', RevokeAllOtherSessionsView.as_view(), name='revoke-all-other-sessions'),

    # ── Manager Management ──────────────────────────────────────────────────────
    # New unified endpoints (preferred)
    path('managers/create/', ManagerCreateView.as_view(), name='manager-create'),
    path('managers/login/', ManagerLoginView.as_view(), name='manager-login'),

    # Legacy endpoints (kept for backward compatibility)
    path('create-manager/', ManagerExecutiveCreateView.as_view(), name='create-manager-executive'),
    path('login-manager/', ManagerExecutiveLoginView.as_view(), name='login-manager-executive'),
    path('manager-executives/<int:pk>/delete/', ManagerExecutiveDeleteView.as_view(), name='delete-manager-executive'),
    path('create-manager-user/', ManagerUserCreateView.as_view(), name='create-manager-user'),
    path('login-manager-user/', ManagerUserLoginView.as_view(), name='login-manager-user'),
    path('manager-users/<int:pk>/delete/', ManagerUserDeleteView.as_view(), name='delete-manager-user'),

    # Permissions update — new clean path + legacy path preserved
    path('permissions/<int:pk>/update/', UpdateAdminPermissionsView.as_view(), name='update-admin-permissions'),
    path('admin/<int:pk>/permissions/', UpdateAdminPermissionsView.as_view(), name='update-admin-permissions-legacy'),

    # Manager list and detail
    path('managers/', ManagerListView.as_view(), name='manager-list'),
    path('managers/<int:pk>/', ManagerDetailView.as_view(), name='manager-detail'),


    # ── Admin Update (superuser manages other admins) ───────────────────────────
    path('admin-update/', AdminUpdateView.as_view(), name='admin-self-update'),
    path('admin/update/<int:pk>/', AdminUpdateView.as_view(), name='admin-update-by-id'),
]
