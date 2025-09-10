from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import Notification


class NotificationService:
    """Service for creating and managing notifications"""

    @staticmethod
    def create_notification(
            recipient,
            content_object,
            notification_type,
            title,
            extra_data=None
    ):
        """Create a new notification"""
        content_type = ContentType.objects.get_for_model(content_object)

        notification = Notification.objects.create(
            recipient=recipient,
            content_type=content_type,
            object_id=content_object.id,
            notification_type=notification_type,
            title=title,
            status='sent',
            sent_time=timezone.now(),
            extra_data=extra_data or {}
        )

        return notification

    @staticmethod
    def create_application_created_notification(application):
        """Create notification when application is created"""
        title = f"Sizning '{application.reward.name}' mukofoti uchun arizangiz muvaffaqiyatli yuborildi."

        extra_data = {
            'reward_name': application.reward.name,
            'area': application.get_area_display(),
            'district': application.district,
            'activity': application.activity
        }

        return NotificationService.create_notification(
            recipient=application.user,
            content_object=application,
            notification_type='application_created',
            title=title,
            extra_data=extra_data
        )

    @staticmethod
    def create_application_in_process_notification(application, old_status):
        """Create notification when application is in process (mahalla, tuman, hudud)"""
        status_messages = {
            'mahalla': 'Arizangiz mahalla bosqichida ko\'rib chiqilmoqda',
            'tuman': 'Arizangiz tuman bosqichida ko\'rib chiqilmoqda',
            'hudud': 'Arizangiz hudud bosqichida ko\'rib chiqilmoqda',
        }

        title = f"Arizangiz ko'rib chiqilmoqda,  Arizangiz {application.get_status_display()} bosqichida."

        extra_data = {
            'reward_name': application.reward.name,
            'old_status': old_status,
            'new_status': application.status,
            'status_display': application.get_status_display()
        }

        return NotificationService.create_notification(
            recipient=application.user,
            content_object=application,
            notification_type='application_updated',
            title=title,
            extra_data=extra_data
        )

    @staticmethod
    def create_application_last_process_notification(application):
        """Create notification when application is in process oxirgi_tasdiqlash"""

        title = "Ariza holati yangilandi"
        extra_data = {
            'reward_name': application.reward.name,
            'updated_date': timezone.now().isoformat()
        }

        return NotificationService.create_notification(
            recipient=application.user,
            content_object=application,
            notification_type='application_updated',
            title=title,
            extra_data=extra_data
        )


    @staticmethod
    def create_application_won_notification(application):
        """Create notification when application is approved (mukofotlangan)"""
        title = (
            f"Tabriklaymiz! Sizning {application.reward.name}' mukofoti uchun arizangiz barcha bosqichlardan muvaffaqiyatli o‘tdi va yakuniy qaror bilan ushbu mukofotga loyiq deb topildingiz.")

        extra_data = {
            'reward_name': application.reward.name,
            'reward_description': application.reward.description,
            'won_date': timezone.now().isoformat()
        }

        return NotificationService.create_notification(
            recipient=application.user,
            content_object=application,
            notification_type='reward_won',
            title=title,
            extra_data=extra_data
        )

    @staticmethod
    def create_application_rejected_notification(application):
        """Create notification when application is rejected (rad_etilgan)"""
        title = f"Afsuski, '{application.reward.name}' mukofoti uchun arizangiz rad etildi."
        # description = f"Afsuski, '{application.reward.name}' mukofoti uchun arizangiz rad etildi."
        # message = f"Hurmatli {application.user.get_full_name()}, sizning '{application.reward.name}' mukofoti uchun arizangiz rad etildi. Boshqa imkoniyatlar uchun kuzatib boring."

        extra_data = {
            'reward_name': application.reward.name,
            'rejected_date': timezone.now().isoformat()
        }

        return NotificationService.create_notification(
            recipient=application.user,
            content_object=application,
            notification_type='application_rejected',
            title=title,
            extra_data=extra_data
        )
