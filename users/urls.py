from django.urls import path
from users.views import *

urlpatterns = [

    path('register-or-login/', RegisterOrLoginView.as_view(), name='register-or-login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('users/logout/', LogoutView.as_view(), name='logout'),
    path('users/<int:user_id>/', UserDetailView.as_view(), name='user-detail'),
    path('admin-user/<int:user_id>/', UserDetailViewAdmin.as_view(), name='user-detail-admin'),
    path('users/me/', UserDetailView.as_view(), name='user-self-detail'),
    path('users/referral-code/', UserReferralCodeView.as_view(), name='user-referral-code'),
    path('user/coin-balance/', UserCoinBalanceView.as_view(), name='user-coin-balance'),
    path('executives/', ExecutiveListAPIView.as_view(), name='executive-list'),
    path('admin/<int:user_id>/update-status/', UpdateUserStatusAPIView.as_view(), name='update-user-status'),#ban / suspend
    path('ratings/<int:executive_id>/', RatingExecutiveView.as_view(), name='manage-rating'),#rating add del list
    path('careers/', CareerListCreateView.as_view(), name='career-list-create'),
    path('careers/<int:pk>/', CareerDetailView.as_view(), name='career-detail'),
    path('carousel-images/', CarouselImageListCreateView.as_view(), name='carousel_image_list_create'),
    path('carousel-images/<int:image_id>/', CarouselImageDetailView.as_view(), name='carousel_image_detail'),
    path('referrals/', ReferralHistoryListView.as_view(), name='referral-history-list'),
    path('users/', UserProfileListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    # User self-deletion
    path("user-delete/<int:user_id>/", DeleteUserAccountView.as_view(), name="delete-user"),
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
    path('executives/favorites/', FavoriteExecutiveView.as_view(), name='favorite-executives'),
    path("executives-ratings/<int:executive_id>/", ExecutiveRatingsAPIView.as_view(), name="executive-ratings"),
    path("carousels", CarouselImageListAPIView.as_view(), name="carousel-images-list"),


]