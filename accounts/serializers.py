import random
import string

from PIL import Image
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import datetime
from .models import CustomUser, PasswordResetCode, PhoneVerification
from .tasks import send_reset_code, send_sms_task
import re

class SignupInitialSerializer(serializers.Serializer):
    """
    Step 1: Collect user data and send SMS verification code
    User fills the complete form here - only once!
    """
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    other_name = serializers.CharField(max_length=50)
    gender = serializers.ChoiceField(choices=CustomUser.Gender.choices)
    email = serializers.EmailField(max_length=100)
    phone_number = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    birth_date = serializers.DateField()
    address = serializers.CharField(max_length=2000, )
    working_place = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    pinfl = serializers.CharField(max_length=14, )
    passport_number = serializers.CharField(max_length=9, )

    class Meta:
        unique_together = ('pinfl', 'passport_number')

    def validate_birth_date(self, birth_date):
        if not birth_date:
            raise serializers.ValidationError("Birth date is required")
        if birth_date >= datetime.date.today():
            raise serializers.ValidationError("Birth date must be before today")

    def validate_working_place(self, working_place):
        if len(working_place) > 2000:
            raise serializers.ValidationError("Working place must be less than 2000 characters")

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def validate_phone_number(self, value):
        # if not value.startswith('+'):
        #     raise serializers.ValidationError("Phone number must include country code with +")

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
        # Create a copy to avoid modifying the original
        user_data_copy = user_data.copy()

        # Extract the required parameters
        password = user_data_copy.pop('password')
        user_data_copy.pop('password_confirm', None)
        email = user_data_copy.pop('email')
        phone_number = user_data_copy.pop('phone_number')

        try:
            with transaction.atomic():
                # Check for existing users
                existing_phone = CustomUser.objects.filter(phone_number=phone_number).exists()
                existing_email = CustomUser.objects.filter(email=email).exists()

                if existing_email:
                    raise serializers.ValidationError("User with this email already exists.")

                if existing_phone:
                    raise serializers.ValidationError("User with this phone number already exists.")

                # Create the user with explicit parameters
                user = CustomUser.objects.create_user(
                    email=email,
                    phone_number=phone_number,
                    password=password,
                    **user_data_copy  # remaining fields like first_name, last_name, etc.
                )

                # Mark verification as used and associate with user
                verification.user = user
                verification.is_used = True
                verification.save()

                return user

        except IntegrityError as e:
            if 'phone_number' in str(e).lower():
                raise serializers.ValidationError("This phone number is already registered.")
            elif 'email' in str(e).lower():
                raise serializers.ValidationError("This email address is already registered.")
            else:
                raise serializers.ValidationError(f"Database constraint error: {str(e)}")


class SigninSerializer(TokenObtainPairSerializer):
    """
    Regular signin with email/password
    """
    username_field = 'phone_number'

    def validate(self, attrs):
        phone_number = attrs.get("phone_number")
        password = attrs.get("password")

        if not phone_number or not password:
            raise AuthenticationFailed("Phone number and password are required")

        user = authenticate(
            request=self.context.get('request'),
            username=phone_number,
            password=password
        )

        if user is None:
            raise AuthenticationFailed("No active account found with the given credentials")

        if not user.is_active:
            raise AuthenticationFailed("Account is inactive")

        data = super().validate(attrs)

        return data

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = [
            "id", "first_name", "last_name", "other_name", "email",
            "address", "birth_date", "phone_number", "profile_picture",
            "gender", "working_place", "passport_number", "pinfl",
            "created_at", "updated_at", "password"
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


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


class UserSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = CustomUser
        fields = [
            'first_name', 'last_name', 'other_name', 'email',
            'address', 'birth_date', 'phone_number', 'gender',
            'working_place', 'passport_number', 'pinfl','profile_picture',
            'password', 'confirm_password'
        ]
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True},
            'email': {'required': True},
            'phone_number': {'required': True},
            'gender': {'required': True},
            'passport_number': {'required': True},
            'pinfl': {'required': True},
            'profile_picture': {'required': False},
        }

    def validate_phone_number(self, value):
        """Validate phone number format"""
        # Remove any spaces or special characters
        cleaned_phone = re.sub(r'[^\d+]', '', value)

        # Basic validation for phone number format
        if not re.match(r'^\+?[\d]{7,15}$', cleaned_phone):
            raise serializers.ValidationError(
                "Phone number must be between 7-15 digits and can include country code with +"
            )
        return value

    def validate_passport_number(self, value):
        """Validate passport number format (9 characters for Uzbekistan)"""
        if not re.match(r'^[A-Z]{2}\d{7}$', value.upper()):
            raise serializers.ValidationError(
                "Passport number must be in format: 2 letters followed by 7 digits (e.g., AA1234567)"
            )
        return value.upper()

    def validate_profile_picture(self, value):
        try:
            img = Image.open(value)
            img.verify()
        except Exception:
            raise serializers.ValidationError("Uploaded file is not a valid image.")

        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("Image size should not exceed 2MB.")

        if img.width > 5000 or img.height > 5000:
            raise serializers.ValidationError("Image resolution too large.")

        return value

    def validate_pinfl(self, value):
        """Validate PINFL (14 digits for Uzbekistan)"""
        if not re.match(r'^\d{14}$', value):
            raise serializers.ValidationError(
                "PINFL must be exactly 14 digits"
            )
        return value

    def validate_email(self, value):
        """Check if email already exists"""
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value.lower()

    def validate_password(self, value):
        """Validate password using Django's built-in validators"""
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(e.messages)
        return value

    def validate(self, attrs):
        """Validate password confirmation and unique constraints"""
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')

        if password != confirm_password:
            raise serializers.ValidationError({
                'confirm_password': 'Password confirmation does not match.'
            })

        # Check unique constraints
        phone_number = attrs.get('phone_number')
        if CustomUser.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError({
                'phone_number': 'User with this phone number already exists.'
            })

        passport_number = attrs.get('passport_number')
        if CustomUser.objects.filter(passport_number=passport_number).exists():
            raise serializers.ValidationError({
                'passport_number': 'User with this passport number already exists.'
            })

        pinfl = attrs.get('pinfl')
        if CustomUser.objects.filter(pinfl=pinfl).exists():
            raise serializers.ValidationError({
                'pinfl': 'User with this PINFL already exists.'
            })

        return attrs

    def create(self, validated_data):
        """Create new user with encrypted password"""
        # Remove confirm_password from validated_data
        validated_data.pop('confirm_password', None)

        # Extract password
        password = validated_data.pop('password')

        # Create user
        user = CustomUser.objects.create_user(
            password=password,
            **validated_data
        )

        return user

    def to_representation(self, instance):
        """Customize response data"""
        data = super().to_representation(instance)
        # Add token to response
        data['tokens'] = instance.token()
        # Remove sensitive fields from response
        data.pop('password', None)
        data.pop('confirm_password', None)
        return data
