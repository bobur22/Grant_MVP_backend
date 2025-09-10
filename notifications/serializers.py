from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Main notification serializer"""

    content_object_data = serializers.SerializerMethodField()
    is_read = serializers.ReadOnlyField()
    time_since = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'title','notification_type',
            'created_time', 'sent_time', 'read_at', 'is_read', 'status',
            'extra_data', 'content_object_data', 'time_since'
        ]
        read_only_fields = [
            'id', 'created_time', 'sent_time', 'status', 'content_object_data'
        ]

    def get_content_object_data(self, obj):
        """Get related object data based on content type"""
        if not obj.content_object:
            return None

        # Handle different content types
        if obj.content_type.model == 'application':
            from applications.serializers import ApplicationDetailSerializer
            return {
                'id': obj.content_object.id,
                'reward_name': obj.content_object.reward.name,
                'status': obj.content_object.status,
                'status_display': obj.content_object.get_status_display(),
                'area': obj.content_object.get_area_display(),
                'district': obj.content_object.district,
                'activity': obj.content_object.activity,
                'created_at': obj.content_object.created_at,
            }

        return {
            'id': obj.content_object.id,
            'model': obj.content_type.model
        }

    def get_time_since(self, obj):
        """Get human readable time since creation"""
        from django.utils.timesince import timesince
        return timesince(obj.created_time)


class NotificationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for notification list"""

    is_read = serializers.ReadOnlyField()
    time_since = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'notification_type',
            'created_time', 'is_read', 'time_since'
        ]

    def get_time_since(self, obj):
        from django.utils.timesince import timesince
        return timesince(obj.created_time)


class MarkAsReadSerializer(serializers.Serializer):
    """Serializer for marking notifications as read"""

    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of notification IDs to mark as read. If empty, all notifications will be marked as read."
    )


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer for notification statistics"""

    total_count = serializers.IntegerField()
    unread_count = serializers.IntegerField()
    read_count = serializers.IntegerField()
    notifications_by_type = serializers.DictField()
    recent_notifications = NotificationListSerializer(many=True)