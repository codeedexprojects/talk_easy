from django.urls import path
from executives.views import *

urlpatterns = [

    path('register-executives/', RegisterExecutiveView.as_view(), name='register-executive'), #reg admin
    path("executive/login/", ExecutiveLoginView.as_view(), name="executive-login"), #login
    path("executive/verify-otp/", ExecutiveVerifyOTPView.as_view(), name="executive-verify-otp"), #verify
    path('executive-logout/<int:executive_id>/', ExecutiveLogoutView.as_view(), name='executive-logout'), #logout
    path('executives/', ExecutiveListAPIView.as_view(), name='executive-list'), #ex list admin
    path('executives/<int:id>/', ExecutiveDetailAPIView.as_view(), name='executive-detail'), #ex details admin
    path('executive/<int:id>/update/', ExecutiveUpdateByIDAPIView.as_view(), name='executive-update-by-id'),
    path('admin-executive/<int:id>/update/', AdminUpdateExecutiveAPIView.as_view(), name='admin-update-executive'),
    path('executive/<int:executive_id>/block-user/<int:user_id>/', BlockUserAPIView.as_view(), name='block-user'),#block
    path('executive/<int:executive_id>/unblock-user/<int:user_id>/', UnblockUserAPIView.as_view(), name='unblock-user'),#unblock
    path('executive/<int:executive_id>/update-status/', UpdateExecutiveStatusAPIView.as_view(), name='update-executive-status'),#update stts - ban/unban-admin
    path('executive/<int:id>/update-online-status/', UpdateExecutiveOnlineStatusAPIView.as_view(), name='update-online-status'),
    path('suspend-executives/<int:id>/', ExecutiveSuspendToggleView.as_view(), name='executive-suspend-toggle'), #suspend or unsuspend

]