from django.db import models

from accounts.models import CustomUser


class File(models.Model):
    file = models.FileField(upload_to='files/', )
    application = models.ForeignKey('Application', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_filename(self):
        return self.file.name

    def __str__(self):
        return self.file.name

    class Meta:
        ordering = ['created_at']
        verbose_name = 'File'
        verbose_name_plural = 'Files'


class Reward(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    image = models.ImageField(upload_to='rewards/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Reward'
        verbose_name_plural = 'Rewards'

    def __str__(self):
        return self.name


class Certificates(models.Model):
    application = models.ForeignKey('Application', on_delete=models.CASCADE)
    file = models.FileField(upload_to='certificates/', )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_filename(self):
        return self.file.name

    def __str__(self):
        return self.file.name

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Certificate'
        verbose_name_plural = 'Certificates'
        db_table = 'certificates'


class Application(models.Model):
    STATUS_CHOICES = (
        ('yuborilgan', 'Yuborilgan'),
        ('mahalla', 'Mahalla jarayonida'),
        ('tuman', 'Tuman'),
        ('hudud', 'Hudud'),
        ('oxirgi_tasdiqlash', 'Oxirgi tasdiqlash'),
        ('mukofotlangan', 'Mukofotlangan'),
        ('rad_etilgan', 'Rad etilgan'),
    )

    AREA_CHOICES = (
        ('Andijon', 'Andijon viloyati'),
        ('Buxoro', 'Buxoro viloyati'),
        ('Fargona', 'Fargʻona viloyati'),
        ('Jizzax', 'Jizzax viloyati'),
        ('Namangan', 'Namangan viloyati'),
        ('Navoiy', 'Navoiy viloyati'),
        ('Qashqadaryo', 'Qashqadaryo viloyati'),
        ("Qoraqalpogiston", 'Qoraqalpogʻiston Respublikasi'),
        ('Samarqand', 'Samarqand viloyati'),
        ('Sirdaryo', 'Sirdaryo viloyati'),
        ('Surxondaryo', 'Surxondaryo viloyati'),
        ('Toshkent', 'Toshkent viloyati'),
        ('Toshkent_shahri', 'Toshkent shahri'),
        ('Xorazm', 'Xorazm viloyati'),
    )

    reward = models.ForeignKey(Reward, on_delete=models.PROTECT, related_name='applications')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_applications')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='yuborilgan')
    area = models.CharField(max_length=20, choices=AREA_CHOICES, )
    district = models.CharField(max_length=200,)
    neighborhood = models.CharField(max_length=200,)
    activity = models.CharField(max_length=200, )
    activity_description = models.TextField()
    recommendation_letter = models.FileField(upload_to='recommendation/', null=True, blank=True)
    source = models.CharField(max_length=200, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'

        constraints = [
            models.UniqueConstraint(
                fields=['user', 'reward'],
                name='unique_user_reward_application'
            )
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Track the original status to detect changes
        self._original_status = self.status if self.pk else None

    def save(self, *args, **kwargs):
        # Check if this is an update and if status changed
        is_new = self._state.adding
        is_status_change = False
        old_status = None

        if not is_new and self.pk:
            old_status = self._original_status
            is_status_change = old_status != self.status

        # Save the instance
        super().save(*args, **kwargs)

        # Handle notifications after save
        if is_new:
            # New application created - handled by signals
            pass
        elif is_status_change and old_status:
            # Status changed - handle notification
            self._handle_status_change_notification(old_status)

        # Update the tracked status
        self._original_status = self.status

    def _handle_status_change_notification(self, old_status):
        """Handle status change notifications"""
        from notifications.services import NotificationService

        new_status = self.status
        in_process_statuses = ['mahalla', 'tuman', 'hudud',]

        if new_status in in_process_statuses:
            NotificationService.create_application_in_process_notification(self, old_status)
        elif new_status == "oxirgi_tasdiqlash":
            NotificationService.create_application_last_process_notification(self)
        elif new_status == 'mukofotlangan':
            NotificationService.create_application_won_notification(self)
        elif new_status == 'rad_etilgan':
            NotificationService.create_application_rejected_notification(self)


    def __str__(self):
        return f"{self.user.get_full_name}'s application"
