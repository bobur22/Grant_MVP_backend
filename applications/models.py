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
    area = models.CharField(max_length=20, choices=AREA_CHOICES, default='Andijon')
    district = models.CharField(max_length=200, null=True)
    neighborhood = models.CharField(max_length=200, null=True)
    activity = models.CharField(max_length=200, null=True)
    activity_description = models.TextField(null=True)
    recommendation_letter = models.FileField(upload_to='recommendation/', null=True, blank=True)
    source = models.CharField(max_length=200)
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

    def __str__(self):
        return f"{self.user.get_full_name}'s application"
