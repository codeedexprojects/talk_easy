from django.urls import path
from executives.views import *

urlpatterns = [

    path('register-executives/', RegisterExecutiveView.as_view(), name='register-executive'), #reg admin
    path("executive/login/", ExecutiveLoginView.as_view(), name="executive-login"), #login
    path("executive/verify-otp/", ExecutiveVerifyOTPView.as_view(), name="executive-verify-otp"), #verify
    path('executive-logout/<int:executive_id>/', ExecutiveLogoutView.as_view(), name='executive-logout'), #logout
    path('executives/', ExecutiveListAPIView.as_view(), name='executive-list'), #ex list admin
    path('executives/<int:id>/', ExecutiveDetailAPIView.as_view(), name='executive-detail'), #ex details admin

    
]