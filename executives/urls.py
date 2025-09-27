from django.urls import path
from executives.views import *

urlpatterns = [

    path("languages/", LanguageListCreateView.as_view(), name="language-list-create"),
    path("languages/<int:pk>/", LanguageDetailView.as_view(), name="language-detail"),
    path('register-executives/', RegisterExecutiveView.as_view(), name='register-executive'), #reg admin
    path("executive/login/", ExecutiveLoginView.as_view(), name="executive-login"), #login
    path("executive/verify-otp/", ExecutiveVerifyOTPView.as_view(), name="executive-verify-otp"), #verify
    path('executive-logout/<int:executive_id>/', ExecutiveLogoutView.as_view(), name='executive-logout'), #logout
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

]