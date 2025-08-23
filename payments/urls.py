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
]
