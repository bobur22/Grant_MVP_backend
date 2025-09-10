from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from applications.models import Application

from accounts.models import CustomUser


class Notification(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    TYPE_CHOICES = [
        ('application_crated', 'Application Created'),
        ('application_updated', 'Application Updated'),
        ('application_rejected', 'Application Rejected'),
        ('reward_won', 'Reward Won'),
    ]

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.IntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    recipient = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='received_notifications')
    # sender = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='sent_notifications', null=True, blank=True)

    notification_type = models.CharField(max_length=30, choices=TYPE_CHOICES)

    title = models.CharField(max_length=200)
    # description = models.TextField(blank=True)

    created_time = models.DateTimeField(auto_now_add=True)

    sent_time = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    extra_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_time']
        indexes = [
            models.Index(fields=['recipient', 'read_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        return f"{self.title} - {self.recipient.email}"

    def mark_as_read(self):
        if not self.read_at:
            self.read_at = timezone.now()
            self.save(update_fields=['read_at'])

    @property
    def is_read(self):
        return self.read_at is not None

    def get_instance_id(self):
        if self.content_object:
            return self.content_object.id
        return None
