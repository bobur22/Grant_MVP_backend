from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient', 'notification_type', 'status', 'is_read', 'created_time')
    list_filter = ('notification_type', 'status', 'read_at', 'created_time')
    search_fields = ('title', 'recipient__email')
    readonly_fields = ('content_type', 'object_id', 'sent_time', 'created_time',)

    def is_read(self, obj):
        return obj.is_read

    is_read.boolean = True