from django.db.models.signals import post_save
from django.dispatch import receiver
from applications.models import Application
from .services import NotificationService


@receiver(post_save, sender=Application)
def handle_application_notifications(sender, instance, created, **kwargs):
    """Handle application notifications based on creation or status changes"""

    if created:
        # Application was just created
        NotificationService.create_application_created_notification(instance)
        return

    update_fields = kwargs.get('update_fields') or []

    if update_fields and 'status' not in update_fields:
        return
    # Get the old instance to compare status
    try:
        old_instance = Application.objects.get(pk=instance.pk)

        # Skip if we can't get the old instance from database
        # (this handles the case where we're updating the instance)
        if hasattr(instance, '_original_status'):
            old_status = instance._original_status
        else:
            # If we don't have the original status tracked, get it from the DB
            # This is a fallback, ideally you'd track original status
            return

    except Application.DoesNotExist:
        return

    # Check different status changes
    # new_status = instance.status
    #
    # # In-process statuses
    # in_process_statuses = ['mahalla', 'tuman', 'hudud']
    #
    # if new_status in in_process_statuses:
    #     NotificationService.create_application_in_process_notification(
    #         instance,
    #         getattr(instance, '_original_status', 'unknown')
    #     )
    # elif new_status == "oxirgi_tasdiqlash":
    #     NotificationService.create_application_last_process_notification(instance)
    #
    # elif new_status == 'mukofotlangan':
    #     NotificationService.create_application_won_notification(instance)
    #
    # elif new_status == 'rad_etilgan':
    #     NotificationService.create_application_rejected_notification(instance)
