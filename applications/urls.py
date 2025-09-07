from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RewardViewSet, FileViewSet, ApplicationViewSet


router = DefaultRouter()
router.register(r'rewards', RewardViewSet, basename='reward')
router.register(r'files', FileViewSet, basename='file')
router.register(r'applications', ApplicationViewSet, basename='application')

urlpatterns = []
urlpatterns += router.urls
