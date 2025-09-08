from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import FileExtensionValidator, MaxLengthValidator
from django.db import models
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken


class CustomUserManager(BaseUserManager):
    def create_user(self, email,phone_number, password=None, **extra_fields):
        if not email:
            raise ValueError('User should have an email address')
        if not phone_number:
            raise ValueError('User should have an phone number')
        email = self.normalize_email(email).lower()
        user = self.model(email=email,phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email,phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if not email:
            raise ValueError('User should have an email address')
        if not phone_number:
            raise ValueError('User should have an phone number')
        return self.create_user(email,phone_number, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    class Gender(models.TextChoices):
        MALE = 'M'
        FEMALE = 'F'

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    other_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    address = models.TextField(validators=[MaxLengthValidator(2000)],)
    birth_date = models.DateField()
    phone_number = models.CharField(max_length=20, unique=True)
    profile_picture = models.ImageField(upload_to='avatars/', blank=True, validators=[
        FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'heic', 'webp', ])],
                                        default='default_imgs/user.png')
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    working_place = models.CharField(max_length=2000, blank=True, null=True)
    passport_number = models.CharField(max_length=9,)
    pinfl = models.CharField(max_length=14,)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []
    objects = CustomUserManager()

    class Meta:
        db_table = 'users'
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def token(self):
        refresh = RefreshToken.for_user(self)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }

    @property
    def get_full_name(self):
        return self.first_name + ' ' + self.last_name


class PhoneVerification(models.Model):
    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="verifications",
        null=True,
        blank=True
    )
    code = models.CharField(max_length=6)
    phone_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    verification_type = models.CharField(
        max_length=20,
        choices=[
            ('signup', 'Signup Verification'),
            ('login', 'Login Verification'),
            ('reset', 'Password Reset'),
        ],
        default='signup'
    )

    def is_valid(self):
        return (self.expires_at > timezone.now()) and not self.is_used

    @classmethod
    def create_code(cls, user, code):
        return cls.objects.create(
            user=user,
            code=code,
            expires_at=timezone.now() + timedelta(minutes=5)
        )

    @classmethod
    def create_signup_code(cls, phone_number, code):
        """Create verification code for signup process (no user yet)"""
        return cls.objects.create(
            user=None,
            phone_number=phone_number,
            code=code,
            verification_type='signup',
            expires_at=timezone.now() + timedelta(minutes=5)
        )

    def __str__(self):
        if self.user:
            return f"Verification for {self.user.email} - {self.code}"
        return f"Signup verification for {self.phone_number} - {self.code}"



class PasswordResetCode(models.Model):
    phone_number = models.CharField(max_length=15)
    code = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return (timezone.now() - self.created_at).seconds < 300
