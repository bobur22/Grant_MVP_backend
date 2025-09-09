# urls.py
from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

from .views import ApplicationStatsView, ApplicationDetailView

router = DefaultRouter()
router.register(r'rewards', views.RewardViewSet, basename='reward')

app_name = 'applications'

urlpatterns = [
    path('rewards/<int:reward_id>/applications/', views.RewardApplicationsView.as_view(), name='reward-applications'),
    path('application/step1/', views.ApplicationStep1View.as_view(), name='application-step1'),
    path('application/step2/', views.ApplicationStep2View.as_view(), name='application-step2'),
    path('application/step3/', views.ApplicationStep3View.as_view(), name='application-step3'),
    path('application/final-review/', views.ApplicationFinalReviewView.as_view(), name='application-final'),
    path('application/status/', views.ApplicationStatusView.as_view(), name='application-status'),
    path('applications/list/', views.ApplicationsListView.as_view(), name='application-list'),
    path('applications/create/', views.ApplicationCreateView.as_view(), name='application-create'),
    path('my-applications/', views.MyApplicationsView.as_view(), name='my-applications'),
    path('applications/stats/', ApplicationStatsView.as_view(), name='application-stats'),
    path('applications/<int:application_id>/', ApplicationDetailView.as_view(), name='application-detail'),

    # File upload
    path('certificate/upload/', views.CertificateUploadView.as_view(), name='certificate-upload'),

    path('clear-draft/', views.clear_draft, name='clear-draft'),
]
urlpatterns += router.urls
