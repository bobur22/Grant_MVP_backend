# notifications/views.py
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q, Count
from django.utils import timezone

from .models import Notification
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    MarkAsReadSerializer,
    NotificationStatsSerializer
)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# class NotificationViewSet(ModelViewSet):
#     """ViewSet for managing notifications"""
#
#     permission_classes = [IsAuthenticated]
#     pagination_class = NotificationPagination
#
#     def get_queryset(self):
#         """Get notifications for the authenticated user"""
#         return Notification.objects.filter(
#             recipient=self.request.user
#         ).select_related('content_type').prefetch_related('content_object')
#
#     def get_serializer_class(self):
#         """Return appropriate serializer based on action"""
#         if self.action == 'list':
#             return NotificationListSerializer
#         return NotificationSerializer
#
#     def list(self, request, *args, **kwargs):
#         """List notifications with filtering options"""
#         queryset = self.get_queryset()
#
#         # Filter by read status
#         is_read = request.query_params.get('is_read')
#         if is_read is not None:
#             if is_read.lower() == 'true':
#                 queryset = queryset.filter(read_at__isnull=False)
#             elif is_read.lower() == 'false':
#                 queryset = queryset.filter(read_at__isnull=True)
#
#         # Filter by notification type
#         notification_type = request.query_params.get('type')
#         if notification_type:
#             queryset = queryset.filter(notification_type=notification_type)
#
#         # Filter by date range
#         date_from = request.query_params.get('date_from')
#         date_to = request.query_params.get('date_to')
#
#         if date_from:
#             queryset = queryset.filter(created_time__gte=date_from)
#         if date_to:
#             queryset = queryset.filter(created_time__lte=date_to)
#
#         # Order by creation time (newest first)
#         queryset = queryset.order_by('-created_time')
#
#         page = self.paginate_queryset(queryset)
#         if page is not None:
#             serializer = self.get_serializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
#
#         serializer = self.get_serializer(queryset, many=True)
#         return Response(serializer.data)
#
#     def retrieve(self, request, *args, **kwargs):
#         """Get single notification and mark as read"""
#         instance = self.get_object()
#
#         # Mark as read when retrieving
#         if not instance.is_read:
#             instance.mark_as_read()
#
#         serializer = self.get_serializer(instance)
#         return Response(serializer.data)
#
#     @action(detail=True, methods=['post'])
#     def mark_as_read(self, request, pk=None):
#         """Mark a single notification as read"""
#         notification = self.get_object()
#         notification.mark_as_read()
#
#         return Response({
#             'message': 'Notification marked as read',
#             'is_read': True
#         })
#
#     @action(detail=False, methods=['post'])
#     def mark_all_as_read(self, request):
#         """Mark multiple or all notifications as read"""
#         serializer = MarkAsReadSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#
#         notification_ids = serializer.validated_data.get('notification_ids')
#         queryset = self.get_queryset().filter(read_at__isnull=True)
#
#         if notification_ids:
#             queryset = queryset.filter(id__in=notification_ids)
#
#         updated_count = queryset.update(read_at=timezone.now())
#
#         return Response({
#             'message': f'{updated_count} notifications marked as read',
#             'updated_count': updated_count
#         })
#
#     @action(detail=False, methods=['get'])
#     def stats(self, request):
#         """Get notification statistics for the user"""
#         queryset = self.get_queryset()
#
#         total_count = queryset.count()
#         unread_count = queryset.filter(read_at__isnull=True).count()
#         read_count = total_count - unread_count
#
#         # Notifications by type
#         notifications_by_type = dict(
#             queryset.values_list('notification_type').annotate(
#                 count=Count('id')
#             )
#         )
#
#         # Recent notifications (last 5)
#         recent_notifications = queryset.order_by('-created_time')[:5]
#
#         data = {
#             'total_count': total_count,
#             'unread_count': unread_count,
#             'read_count': read_count,
#             'notifications_by_type': notifications_by_type,
#             'recent_notifications': recent_notifications
#         }
#
#         serializer = NotificationStatsSerializer(data)
#         return Response(serializer.data)
#
#     @action(detail=False, methods=['get'])
#     def unread(self, request):
#         """Get only unread notifications"""
#         queryset = self.get_queryset().filter(read_at__isnull=True)
#
#         page = self.paginate_queryset(queryset)
#         if page is not None:
#             serializer = NotificationListSerializer(page, many=True)
#             return self.get_paginated_response(serializer.data)
#
#         serializer = NotificationListSerializer(queryset, many=True)
#         return Response(serializer.data)
#
#     def destroy(self, request, *args, **kwargs):
#         """Delete a notification"""
#         instance = self.get_object()
#         self.perform_destroy(instance)
#         return Response(status=status.HTTP_204_NO_CONTENT)
#
#     @action(detail=False, methods=['delete'])
#     def clear_all(self, request):
#         """Clear all notifications for the user"""
#         queryset = self.get_queryset()
#         deleted_count = queryset.count()
#         queryset.delete()
#
#         return Response({
#             'message': f'{deleted_count} notifications cleared',
#             'deleted_count': deleted_count
#         })
#


class NotificationListView(generics.ListAPIView):
    """List view for notifications with filtering and stats"""
    serializer_class = NotificationListSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get_queryset(self):
        queryset = Notification.objects.filter(
            recipient=self.request.user
        ).select_related('content_type').prefetch_related('content_object')

        return queryset.order_by('-created_time')

    def list(self, request, *args, **kwargs):
        """Enhanced list with notification stats"""
        queryset = self.get_queryset()
        total_count = Notification.objects.filter(recipient=request.user).count()
        unread_count = Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True
        ).count()

        # Paginate
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response_data = self.get_paginated_response(serializer.data)
            # Add stats to paginated response
            response_data.data['stats'] = {
                'total_count': total_count,
                'unread_count': unread_count,
                'read_count': total_count - unread_count
            }
            return response_data

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'stats': {
                'total_count': total_count,
                'unread_count': unread_count,
                'read_count': total_count - unread_count
            }
        })


class NotificationDetailView(generics.RetrieveAPIView):
    """Detail view for notifications - marks as read when accessed"""
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        was_unread = not instance.is_read

        # Mark as read when accessing detail
        if was_unread:
            instance.mark_as_read()

        serializer = self.get_serializer(instance)
        response_data = serializer.data
        response_data['was_marked_as_read'] = was_unread

        return Response(response_data)


class MarkNotificationAsReadView(APIView):
    """Mark single notification as read"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def patch(self, request, *args, **kwargs):
        notification = get_object_or_404(self.get_queryset(), pk=kwargs['pk'])
        was_unread = not notification.is_read

        if was_unread:
            notification.mark_as_read()

        return Response({
            'success': True,
            'message': 'Xabar o\'qilgan deb belgilandi' if was_unread else 'Xabar allaqachon o\'qilgan edi',
            'was_unread': was_unread,
            'is_read': True
        })


class MarkAllNotificationsAsReadView(generics.GenericAPIView):
    """Mark all notifications as read for the user"""
    permission_classes = [IsAuthenticated]
    serializer_class = MarkAsReadSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        notification_ids = serializer.validated_data.get('notification_ids', [])

        # Get unread notifications
        unread_notifications = Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True
        )

        # If specific IDs provided, filter by them
        if notification_ids:
            unread_notifications = unread_notifications.filter(id__in=notification_ids)

        # Count and update
        count_before = unread_notifications.count()
        updated_count = unread_notifications.update(read_at=timezone.now())

        return Response({
            'success': True,
            'message': f'{updated_count} ta xabar o\'qilgan deb belgilandi',
            'updated_count': updated_count,
            'total_unread_before': count_before
        })


class NotificationStatsView(generics.GenericAPIView):
    """Get notification statistics for the user"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user_notifications = Notification.objects.filter(recipient=request.user)

        total_count = user_notifications.count()
        unread_count = user_notifications.filter(read_at__isnull=True).count()
        read_count = total_count - unread_count

        return Response({
            'total_count': total_count,
            'unread_count': unread_count,
            'read_count': read_count,
        })