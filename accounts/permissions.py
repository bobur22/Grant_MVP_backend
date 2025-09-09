from rest_framework import permissions


class IsSelfOrAdmin(permissions.BasePermission):
    """
    - Regular users: can only see/update their own data
    - Staff/Admin: full CRUD
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        return obj == request.user
