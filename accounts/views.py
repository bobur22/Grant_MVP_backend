import random
import string
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PhoneVerification
from .serializers import (ResetPasswordSerializer, SendResetCodeSerializer,
                          SigninSerializer, SignupInitialSerializer,
                          SignupVerifySerializer, UserSerializer)
from .tasks import send_sms_task


class SignupStep1View(APIView):
    """
    Step 1: User fills complete signup form and gets SMS
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignupInitialSerializer(data=request.data)
        if serializer.is_valid():
            try:
                result = serializer.save()

                # Store ALL user data in cache - this is the key fix!
                cache_key = f"signup_data_{result['verification_id']}"
                cache.set(cache_key, result['user_data'], timeout=300)  # 5 minutes

                return Response({
                    'success': True,
                    'message': 'Verification code sent to your phone',
                    'verification_id': result['verification_id'],
                    'expires_at': result['expires_at']
                }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Failed to send SMS. Please try again.',
                    "errors": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class SignupStep2View(APIView):
    """
    Step 2: User only enters SMS code - that's it!
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # User only sends verification_id and code
        serializer = SignupVerifySerializer(data=request.data)

        if serializer.is_valid():
            try:
                verification_id = serializer.validated_data['verification_id']
                verification = serializer.validated_data['verification']

                # Get the cached user data
                cache_key = f"signup_data_{verification_id}"
                cached_user_data = cache.get(cache_key)

                if not cached_user_data:
                    return Response({
                        'success': False,
                        'message': 'Session expired. Please start signup process again.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Create user using cached data
                user = serializer.create_user(cached_user_data, verification)

                # Clear cached data
                cache.delete(cache_key)

                # Generate tokens for immediate login
                tokens = user.token()

                return Response({
                    'success': True,
                    'message': 'Account created successfully! You are now logged in.',
                    'tokens': tokens,
                    'user': UserSerializer(user).data
                }, status=status.HTTP_201_CREATED)

            except serializers.ValidationError as e:
                return Response({
                    'success': False,
                    'message': str(e)
                }, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Failed to create account. Please try again.',
                    "errors": str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ResendSMSView(APIView):
    """
    Resend SMS verification code
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        verification_id = request.data.get('verification_id')

        try:
            # Get cached user data
            cache_key = f"signup_data_{verification_id}"
            cached_data = cache.get(cache_key)

            if not cached_data:
                return Response({
                    'success': False,
                    'message': 'Session expired. Please start signup process again.'
                }, status=status.HTTP_400_BAD_REQUEST)

            phone_number = cached_data.get('phone_number')

            # Generate new code
            code = ''.join(random.choices(string.digits, k=6))

            # Mark old verification as used
            PhoneVerification.objects.filter(
                id=verification_id,
                is_used=False
            ).update(is_used=True)

            # Create new verification
            new_verification = PhoneVerification.create_signup_code(phone_number, code)

            # Update cache with new verification_id
            new_cache_key = f"signup_data_{new_verification.id}"
            cache.set(new_cache_key, cached_data, timeout=300)
            cache.delete(cache_key)  # Remove old cache

            # Send SMS
            send_sms_task.delay(phone_number, code)

            return Response({
                'success': True,
                'message': 'New verification code sent',
                'verification_id': new_verification.id,
                'expires_at': new_verification.expires_at
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Failed to resend SMS. Please try again.'
            }, status=status.HTTP_400_BAD_REQUEST)


class SigninView(TokenObtainPairView):
    """
    Regular signin for existing users
    """
    serializer_class = SigninSerializer



class SendPasswordResetCodeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SendResetCodeSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Code has been sent to your phone number"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Password has been successfully changed"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
