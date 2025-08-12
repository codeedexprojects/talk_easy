from django.urls import path
from users.views import *

urlpatterns = [

    path('register-or-login/', RegisterOrLoginView.as_view(), name='register-or-login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('users/logout/', LogoutView.as_view(), name='logout'),
    path('users/<int:user_id>/', UserDetailView.as_view(), name='user-detail'),
    path('users/me/', UserDetailView.as_view(), name='user-self-detail'),




]