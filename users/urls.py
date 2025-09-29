from django.urls import path
from users.views import *

urlpatterns = [

    path('register-or-login/', RegisterOrLoginView.as_view(), name='register-or-login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('users/logout/', LogoutView.as_view(), name='logout'),
    path('users/<int:user_id>/', UserDetailView.as_view(), name='user-detail'),
    path('users/me/', UserDetailView.as_view(), name='user-self-detail'),
    path('users/referral-code/', UserReferralCodeView.as_view(), name='user-referral-code'),
    path('user/coin-balance/', UserCoinBalanceView.as_view(), name='user-coin-balance'),
    path('executives/', ExecutiveListAPIView.as_view(), name='executive-list'),
    path('admin/<int:user_id>/update-status/', UpdateUserStatusAPIView.as_view(), name='update-user-status'),#ban / suspend
    path('favourites/<int:user_id>/', FavouriteExecutiveView.as_view(), name='list-favourites'),#list fav ex
    path('favourites/<int:user_id>/<int:executive_id>/', FavouriteExecutiveView.as_view(), name='manage-favourite'),#add/rem fav ex
    path('ratings/<int:executive_id>/', RatingExecutiveView.as_view(), name='manage-rating'),#rating add del list
    path('careers/', CareerListCreateView.as_view(), name='career-list-create'),
    path('careers/<int:pk>/', CareerDetailView.as_view(), name='career-detail'),
    path('carousel-images/', CarouselImageListCreateView.as_view(), name='carousel_image_list_create'),
    path('carousel-images/<int:image_id>/', CarouselImageDetailView.as_view(), name='carousel_image_detail'),
    path('referrals/', ReferralHistoryListView.as_view(), name='referral-history-list'),
    path('users/', UserProfileListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    # User self-deletion
    path('users/delete-account/',UserSoftDeleteView.as_view(),name='user-self-delete'),    
    # Admin delete specific user
    path('users/<int:user_id>/delete/',UserSoftDeleteView.as_view(),name='admin-user-delete'),    
    # Admin restore user account
    path('users/<int:user_id>/restore/',UserAccountRestoreView.as_view(),name='admin-user-restore'),    
    # Admin bulk delete users
    path('users/bulk-delete/',UserBulkSoftDeleteView.as_view(),name='admin-bulk-delete-users'),    
    # Admin view deleted users list
    path('admin/deleted-users/',DeletedUsersListView.as_view(),name='admin-deleted-users-list'),    
    # Admin deletion statistics
    path('admin/users/deletion-stats/',UserDeletionStatsView.as_view(),name='admin-user-deletion-stats'),    
    # Check user account status
    path('users/account-status/',UserAccountStatusView.as_view(),name='user-account-status'),    
    # Admin check specific user status
    path('users/<int:user_id>/status/',UserAccountStatusView.as_view(),name='admin-user-status'),


]