from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (ResendSMSView, ResetPasswordView,
                    SendPasswordResetCodeView, SigninView, SignupStep1View,
                    SignupStep2View, UserViewSet)
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
urlpatterns = [

    path('signup/step1/', SignupStep1View.as_view(), name='signup_step1'),
    path('signup/step2/', SignupStep2View.as_view(), name='signup_step2'),
    path('signup/resend-sms/', ResendSMSView.as_view(), name='resend_sms'),

    path('signin/', SigninView.as_view(), name='signin'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('send-reset-code/', SendPasswordResetCodeView.as_view(), name='send-reset-code'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
]

urlpatterns += router.urls
