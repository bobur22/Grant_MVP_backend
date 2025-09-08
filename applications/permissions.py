from rest_framework import permissions


class RewardPermission(permissions.BasePermission):
    """
    Custom permission for Reward model:
    - Admin/Staff: Full CRUD operations
    - Regular users: List and Retrieve only
    """

    def has_permission(self, request, view):
        # Allow authenticated users to list and retrieve
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Only admin/staff can create, update, delete
        return request.user and (request.user.is_staff or request.user.is_superuser)

    def has_object_permission(self, request, view, obj):
        # Allow authenticated users to retrieve
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated

        # Only admin/staff can modify
        return request.user and (request.user.is_staff or request.user.is_superuser)
