from django.urls import path
from .views import *

urlpatterns = [
    #  Category
    path('categories/', RechargePlanCategoryListCreateAPIView.as_view(), name='category-list-create'),
    path('categories/<int:pk>/', RechargePlanCategoryDetailAPIView.as_view(), name='category-detail'),
    path('categories/<int:pk>/delete/', RechargePlanCategoryDeleteAPIView.as_view(), name='category-delete'),

    #  Plan
    path('plans/', RechargePlanListCreateAPIView.as_view(), name='plan-list-create'),
    path('plans/<int:pk>/', RechargePlanDetailAPIView.as_view(), name='plan-detail'),
    path('plans/<int:pk>/delete/', RechargePlanDeleteAPIView.as_view(), name='plan-delete'),

    path("recharge-plan-list/", RechargePlansView.as_view(), name="recharge-plans"),
    path('recharge/initiate/', UserRechargeView.as_view(), name='initiate-recharge'),#recharge coin-user
    path('recharge/verify/', VerifyRechargePaymentView.as_view(), name='verify-recharge'),#verfiy
    path('webhook/razorpay/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),  # Webhook endpoint

    path("redemption-options/", RedemptionOptionListCreateAPIView.as_view(), name="redemption-option-list-create"),
    path("redemption-options/<int:pk>/", RedemptionOptionDetailAPIView.as_view(), name="redemption-option-detail"),

    path("redemption-list/", RedemptionOptionListViewExecutive.as_view(), name="redemption-option-list-create"),
    path("executive/redeem/", ExecutiveRedeemAPIView.as_view(), name="executive-redeem"),
    path("executive/redeem/history/", ExecutiveRedeemHistoryAPIView.as_view(), name="executive-redeem-history"),

    path("admin/redeems/", AdminRedeemListUpdateAPIView.as_view(), name="admin-redeem-list"),  # list
    path("admin/redeems/<int:pk>/", AdminRedeemListUpdateAPIView.as_view(), name="admin-redeem-update"),  # update
    path('recharge-history/<int:user_id>/', UserRechargeHistoryViewAdmin.as_view(), name='recharge-history'),#admin
    path('recharge-history/', UserRechargeHistoryView.as_view(), name='recharge-history'),#user

    path('admin/recharge/', AdminRechargeView.as_view(), name='admin-recharge'),#recharge by admin
    path('analytics/', RechargeAnalyticsView.as_view(), name='recharge-analytics'),
    path("recharges/", UserRechargeListView.as_view(), name="recharge-list"),

]
