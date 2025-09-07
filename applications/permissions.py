from rest_framework import permissions

class IsOwnerOrStaff(permissions.BasePermission):
    """
    Custom permission to only allow owners of an application or staff to view it.
    """

    def has_object_permission(self, request, view, obj):
        # Staff and admin can access all applications
        if request.user.is_staff or request.user.is_superuser:
            return True

        # Users can only access their own applications
        return obj.user == request.user
