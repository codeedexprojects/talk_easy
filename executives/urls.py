from django.urls import path
from executives.views import *

urlpatterns = [

    path("languages/", LanguageListCreateView.as_view(), name="language-list-create"),
    path("list-languages/", LanguageListView.as_view(), name="language-list"),

    path("languages/<int:pk>/", LanguageDetailView.as_view(), name="language-detail"),
    path('register-executives/', RegisterExecutiveView.as_view(), name='register-executive'), #reg admin (LEGACY - live in production)
    path("executive/login/", ExecutiveLoginView.as_view(), name="executive-login"), #login (LEGACY - live in production, OTP-based)
    path("executive/verify-otp/", ExecutiveVerifyOTPView.as_view(), name="executive-verify-otp"), #verify (LEGACY - live in production)

    # --- NEW (v2) executive auth flow: OTP requested + verified BEFORE the account is
    # created, login is mobile_number + password only ---
    path("executive/send-registration-otp/", SendRegistrationOTPView.as_view(), name="executive-send-registration-otp"),
    path('register-executives-v2/', RegisterExecutiveV2View.as_view(), name='register-executive-v2'),
    path("executive/login-v2/", ExecutiveLoginV2View.as_view(), name="executive-login-v2"),

    # --- NEW: executive forgot-password (OTP-based, 3 steps) ---
    path("executive/forgot-password/request-otp/", ExecutiveForgotPasswordRequestOTPView.as_view(), name="executive-forgot-password-request-otp"),
    path("executive/forgot-password/verify-otp/", ExecutiveForgotPasswordVerifyOTPView.as_view(), name="executive-forgot-password-verify-otp"),
    path("executive/forgot-password/reset/", ExecutiveForgotPasswordResetView.as_view(), name="executive-forgot-password-reset"),

    path('executive/logout/', ExecutiveLogoutView.as_view(), name='executive-logout-self'), #logout (identity from token)
    path('executive-logout/<int:executive_id>/', ExecutiveLogoutView.as_view(), name='executive-logout'), #logout (LEGACY path form)
    path('executives/', ExecutiveListAPIView.as_view(), name='executive-list'), #ex list admin
    path('executives/<int:id>/', ExecutiveDetailAPIView.as_view(), name='executive-detail'), #ex details admin
    path('executive/<int:id>/update/', ExecutiveUpdateByIDAPIView.as_view(), name='executive-update-by-id'),
    path('admin-executive/<int:id>/update/', AdminUpdateExecutiveAPIView.as_view(), name='admin-update-executive'),
    path('executive/block-user/<int:user_id>/', BlockUserAPIView.as_view(), name='block-user'),#block user
    path('executive/unblock-user/<int:user_id>/', UnblockUserAPIView.as_view(), name='unblock-user'),#unblock user
    path('executive/<int:executive_id>/update-status/', UpdateExecutiveStatusAPIView.as_view(), name='update-executive-status'),#update stts - ban/unban-admin
    path('executive/status/', UpdateExecutiveOnlineStatusAPIView.as_view(), name='update-executive-status'),#online /offline
    path('suspend-executives/<int:id>/', ExecutiveSuspendToggleView.as_view(), name='executive-suspend-toggle'), #suspend or unsuspend
    # Upload/Update profile picture (with executive ID)
    path('profile-picture/<int:executive_id>/',ExecutiveProfilePictureUploadView.as_view(),name='executive-profile-picture'),   
    # Upload/Update profile picture (for authenticated executive without ID)
    path('my-profile-picture/',ExecutiveProfilePictureUploadView.as_view(), name='my-executive-profile-picture'),    
    # Get profile picture status (with executive ID)
    path('profile-picture/status/<int:executive_id>/',ExecutiveProfilePictureStatusView.as_view(),name='executive-profile-picture-status'),    
    # Get profile picture status (for authenticated executive)
    path('my-profile-picture/status/',ExecutiveProfilePictureStatusView.as_view(),name='my-executive-profile-picture-status'),
    #admin
    path('admin/profile-pictures/',AdminProfilePictureListView.as_view(),name='admin-profile-pictures-list'),    
    # Get specific profile picture details
    path('admin/profile-pictures/<int:picture_id>/',AdminProfilePictureDetailView.as_view(),name='admin-profile-picture-detail'),  
    # Approve profile picture
    path('admin/profile-pictures/<int:picture_id>/approve/',AdminProfilePictureApproveView.as_view(),name='admin-profile-picture-approve'),   
    # Reject profile picture
    path('admin/profile-pictures/<int:picture_id>/reject/',AdminProfilePictureRejectView.as_view(),name='admin-profile-picture-reject'),   
    # Bulk actions (approve/reject multiple)
    path('admin/profile-pictures/bulk-action/',AdminProfilePictureBulkActionView.as_view(),name='admin-profile-pictures-bulk-action'),   
    # Get statistics
    path('admin/profile-pictures/stats/',AdminProfilePictureStatsView.as_view(),name='admin-profile-pictures-stats'),
    path("executives/status/", ExecutiveStatusAPIView.as_view(), name="executive-status"),
    path("executives/<int:id>/stats/", ExecutiveStatsDetailView.as_view(), name="executive-stats-detail"),
    path("executives-blocked-users/<int:executive_id>/", BlockedUsersListByExecutiveAPIView.as_view(), name="blocked-users-by-executive"),
    path("executive/blocked-users/", BlockedUsersListAPIView.as_view(), name="blocked-users"),
    path('blocked-users/', AllBlockedUsersListView.as_view(), name='all-blocked-users'),
    path('search/', ExecutiveSearchView.as_view(), name='executive-search'),
    path('analytics/', ExecutiveAnalyticsView.as_view(), name='executive-analytics'),
    
    # Pricing Management URLs (Admin Only)
    path('pricing/global/', GlobalPricingView.as_view(), name='global-pricing'),
    path('pricing/schedules/', RateScheduleListCreateView.as_view(), name='rate-schedule-list-create'),
    path('pricing/schedules/<int:pk>/', RateScheduleDetailView.as_view(), name='rate-schedule-detail'),

]