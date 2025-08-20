from django.urls import path
from .views import SuperuserLoginView

urlpatterns = [
    path("admin/login/", SuperuserLoginView.as_view(), name="super_admin_login"),
]
