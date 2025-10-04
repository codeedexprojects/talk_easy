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
    path("user-recharge/", UserRechargeView.as_view(), name="user-recharge"),

    path("redemption-options/", RedemptionOptionListCreateAPIView.as_view(), name="redemption-option-list-create"),
    path("redemption-options/<int:pk>/", RedemptionOptionDetailAPIView.as_view(), name="redemption-option-detail"),
]