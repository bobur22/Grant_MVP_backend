import random
import string
from datetime import timedelta

from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import CustomUser, PasswordResetCode, PhoneVerification
from .tasks import send_reset_code, send_sms_task


class SignupInitialSerializer(serializers.Serializer):
    """
    Step 1: Collect user data and send SMS verification code
    User fills the complete form here - only once!
    """
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    address = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def validate_phone_number(self, value):
        if not value.startswith('+'):
            raise serializers.ValidationError("Phone number must include country code with +")

        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("User with this phone number already exists.")
        return value

    def validate(self, attrs):
        password = attrs.get('password')
        password_confirm = attrs.get('password_confirm')

        if password != password_confirm:
            raise serializers.ValidationError("Passwords do not match")

        return attrs

    def save(self):
        """
        Store user data and send SMS verification code
        """
        phone_number = self.validated_data['phone_number']

        # Generate 6-digit code
        code = ''.join(random.choices(string.digits, k=6))

        # Invalidate any existing signup verifications for this phone number
        PhoneVerification.objects.filter(
            phone_number=phone_number,
            verification_type='signup',
            is_used=False
        ).update(is_used=True)

        # Create new signup verification (no user yet)
        verification = PhoneVerification.create_signup_code(phone_number, code)

        # Send SMS asynchronously
        send_sms_task.delay(phone_number, code)

        return {
            'verification_id': verification.id,
            'phone_number': phone_number,
            'expires_at': verification.expires_at,
            'user_data': self.validated_data
        }


class SignupVerifySerializer(serializers.Serializer):
    """
    Step 2: Only verify SMS code - no form data needed!
    """
    verification_id = serializers.IntegerField()
    code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        verification_id = attrs.get('verification_id')
        code = attrs.get('code')

        try:
            verification = PhoneVerification.objects.get(
                id=verification_id,
                code=code,
                user=None,
                verification_type='signup',
                is_used=False
            )
        except PhoneVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired verification code")

        if not verification.is_valid():
            raise serializers.ValidationError("Verification code has expired")

        attrs['verification'] = verification
        return attrs

    def create_user(self, user_data, verification):
        """
        Create the user account using cached data
        """
        # Remove password_confirm from user_data
        password = user_data.pop('password')
        user_data.pop('password_confirm', None)  # Remove if exists

        # Double-check email and phone are still available (race condition protection)
        if CustomUser.objects.filter(email=user_data['email']).exists():
            raise serializers.ValidationError("User with this email already exists.")

        if CustomUser.objects.filter(phone_number=user_data['phone_number']).exists():
            raise serializers.ValidationError("User with this phone number already exists.")

        # Create the user
        user = CustomUser.objects.create_user(
            password=password,
            **user_data
        )

        # Mark verification as used and associate with user
        verification.user = user
        verification.is_used = True
        verification.save()

        return user


class SigninSerializer(TokenObtainPairSerializer):
    """
    Regular signin with email/password
    """
    username_field = 'email'

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        if not email or not password:
            raise AuthenticationFailed("Email and password are required")

        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )

        if user is None:
            raise AuthenticationFailed("No active account found with the given credentials")

        if not user.is_active:
            raise AuthenticationFailed("Account is inactive")

        data = super().validate(attrs)

        # Add custom user data to response
        data.update({
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'phone_number': user.phone_number,
            }
        })

        return data


class UserSerializer(serializers.ModelSerializer):
    """
    For returning user data
    """

    class Meta:
        model = CustomUser
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'phone_number',
            'birth_date',
            'address',
            'profile_picture',
        )
        read_only_fields = ('id', 'email')


class SendResetCodeSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)

    def validate_phone_number(self, value):
        if not CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("There is no active user with this phone number")
        return value

    def save(self, **kwargs):
        phone_number = self.validated_data['phone_number']
        code = str(random.randint(100000, 999999))
        PasswordResetCode.objects.create(phone_number=phone_number, code=code)
        send_reset_code.delay(phone_number, code)
        return code


class ResetPasswordSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        phone_number = data.get("phone_number")
        code = data.get("code")
        try:
            reset_code = PasswordResetCode.objects.filter(phone_number=phone_number, code=code).latest("created_at")
        except PasswordResetCode.DoesNotExist:
            raise serializers.ValidationError({"code": "Invalid code"})

        if not reset_code.is_valid():
            raise serializers.ValidationError({"code": "The code is expired"})

        data["reset_code"] = reset_code
        return data

    def save(self, **kwargs):
        phone_number = self.validated_data["phone_number"]
        new_password = self.validated_data["new_password"]
        reset_code = self.validated_data["reset_code"]

        user = CustomUser.objects.get(phone_number=phone_number)
        user.password = make_password(new_password)
        user.save()
        reset_code.delete()
        return user
