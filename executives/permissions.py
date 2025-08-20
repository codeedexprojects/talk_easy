from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and 
            user.is_authenticated and 
            getattr(user, 'role', None) == 'superuser'
        )