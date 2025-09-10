from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

urlpatterns = [
    path('list/', views.NotificationListView.as_view(), name='notification-list'),
    path('<int:pk>/', views.NotificationDetailView.as_view(), name='notification-detail'),

    # Mark as read endpoints
    path('<int:pk>/mark-as-read/', views.MarkNotificationAsReadView.as_view(),
         name='notification-mark-read'),
    path('mark-all-as-read/', views.MarkAllNotificationsAsReadView.as_view(),
         name='notifications-mark-all-read'),

    # Stats endpoint
    path('stats/', views.NotificationStatsView.as_view(), name='notification-stats'),
]