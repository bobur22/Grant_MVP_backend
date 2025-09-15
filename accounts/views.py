import random
import string
from datetime import timedelta

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, serializers, status, viewsets, generics
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PhoneVerification, CustomUser
from .permissions import IsSelfOrAdmin
from .serializers import (ResetPasswordSerializer, SendResetCodeSerializer,
                          SigninSerializer, SignupInitialSerializer,
                          SignupVerifySerializer, UserSerializer, UserSignupSerializer)
from .tasks import send_sms_task


class UserViewSet(viewsets.ModelViewSet):
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ["list", "create"]:
            permission_classes = [IsAdminUser]
        elif self.action in ["retrieve", "update", "partial_update", "destroy", "me"]:
            permission_classes = [IsAuthenticated, IsSelfOrAdmin]
        else:
            permission_classes = [IsAuthenticated]
        return [p() for p in permission_classes]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return CustomUser.objects.all()
        return CustomUser.objects.filter(id=user.id)

    @action(detail=False, methods=["get", "put", "patch", "delete"], url_path="me")
    def me(self, request):
        """Endpoint for logged-in user to manage their own profile"""
        user = request.user

        if request.method == "GET":
            serializer = self.get_serializer(user)
            return Response(serializer.data)

        elif request.method in ["PUT", "PATCH"]:
            serializer = self.get_serializer(user, data=request.data, partial=(request.method == "PATCH"))
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)

        elif request.method == "DELETE":
            user.delete()
            return Response({"detail": "Account deleted successfully."}, status=status.HTTP_204_NO_CONTENT)



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

                cache_key = f"signup_data_{result['verification_id']}"
                cache.set(cache_key, result['user_data'], timeout=300)

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

            except IntegrityError as e:
                if 'phone_number' in str(e).lower():
                    message = "This phone number is already registered."
                elif 'email' in str(e).lower():
                    message = "This email address is already registered."
                else:
                    message = "A user with this information already exists."

                return Response({
                    'success': False,
                    'message': message
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


class UserSignupView(generics.CreateAPIView):
    """
    User registration endpoint
    """
    queryset = CustomUser.objects.all()
    serializer_class = UserSignupSerializer
    permission_classes = [AllowAny]

    @swagger_auto_schema(
        operation_summary="Register new user",
        operation_description="Create a new user account with the provided information",
        responses={
            201: openapi.Response(
                description="User created successfully",
                schema=UserSignupSerializer
            ),
            400: openapi.Response(
                description="Bad Request - Validation errors",
                examples={
                    "application/json": {
                        "message": "Registration failed",
                        "errors": {
                            "email": ["User with this email already exists."],
                            "phone_number": ["User with this phone number already exists."]
                        }
                    }
                }
            )
        }
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        """Create new user account"""
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    'message': 'User created successfully',
                    'user': serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        return Response(
            {
                'message': 'Registration failed',
                'errors': serializer.errors
            },
            status=status.HTTP_400_BAD_REQUEST
        )