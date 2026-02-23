from rest_framework import permissions

class IsAdminUser(permissions.BasePermission):
    """
    Grants access to superusers and all managers (any level).
    Use admin.is_manager_executive / admin.is_manager_user for finer-grained checks inside views.
    """
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                getattr(user, 'role', None) == 'superuser'
                or getattr(user, 'is_manager', False)   # covers both executive & user levels
            )
        )