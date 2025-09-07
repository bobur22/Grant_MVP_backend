from django.db import models

from accounts.models import CustomUser


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


class File(models.Model):
    file = models.FileField(upload_to='files/',)
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




class Application(models.Model):
    STATUS_CHOICES = (
    ('pending', 'Pending'),
    ('in_progress', 'In Progress'),
    ('accepted', 'Accepted'),
    ('rejected', 'Rejected'),
   )

    reward = models.ForeignKey(Reward, on_delete=models.PROTECT, related_name='applications')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='user_applications')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    source = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'

    def __str__(self):
        return f"{self.user.get_full_name}'s application"

