from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from .models import Reward, File, Application
from .serializers import (
    RewardSerializer, FileSerializer, ApplicationListSerializer,
    ApplicationCreateSerializer, ApplicationDetailSerializer,
    ApplicationStatusUpdateSerializer
)
from .permissions import IsOwnerOrStaff


class RewardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving rewards.
    Only read operations are allowed for rewards.
    """
    queryset = Reward.objects.all()
    serializer_class = RewardSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'name']
    ordering = ['-created_at']



    def list(self, request, *args, **kwargs):
        """List all available rewards"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if getattr(self, 'swagger_fake_view', False):
                return queryset.none()

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'success': True,
                'message': 'Rewards retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving rewards',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        """Retrieve a specific reward"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response({
                'success': True,
                'message': 'Reward retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving reward',
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)


class FileViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing files.
    Users can upload and manage their files.
    """
    queryset = File.objects.all()
    serializer_class = FileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        """Upload a new file"""
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                with transaction.atomic():
                    file_instance = serializer.save()

                return Response({
                    'success': True,
                    'message': 'File uploaded successfully',
                    'data': serializer.data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'File upload failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error uploading file',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        """List all files"""
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            if getattr(self, 'swagger_fake_view', False):
                return queryset.none()
            return Response({
                'success': True,
                'message': 'Files retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving files',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplicationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing applications.
    - Users can create and view their own applications
    - Staff/Admin can view all applications and update status
    """
    queryset = Application.objects.select_related('reward', 'user', 'file').all()
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'reward']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'source']
    ordering_fields = ['created_at', 'updated_at', 'status']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return ApplicationCreateSerializer
        elif self.action in ['update_status']:
            return ApplicationStatusUpdateSerializer
        elif self.action == 'retrieve':
            return ApplicationDetailSerializer
        return ApplicationListSerializer

    def get_queryset(self):
        """
        Filter queryset based on user permissions:
        - Staff/Admin: see all applications
        - Regular users: see only their own applications
        """
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()

        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        else:
            return queryset.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """List applications based on user permissions"""
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)

            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)

            message = 'All applications retrieved successfully' if request.user.is_staff else 'Your applications retrieved successfully'

            return Response({
                'success': True,
                'message': message,
                'data': serializer.data,
                'total_count': queryset.count()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving applications',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def create(self, request, *args, **kwargs):
        """Create a new application with files"""
        try:
            serializer = self.get_serializer(data=request.data)

            if serializer.is_valid():
                # Check if user already has a pending/in_progress application for this reward
                existing_application = Application.objects.filter(
                    user=request.user,
                    reward=serializer.validated_data['reward'],
                    status__in=['pending', 'in_progress']
                ).exists()

                if existing_application:
                    return Response({
                        'success': False,
                        'message': 'You already have a pending or in-progress application for this reward',
                    }, status=status.HTTP_400_BAD_REQUEST)

                with transaction.atomic():
                    application = serializer.save()

                # Use detail serializer for response
                response_serializer = ApplicationDetailSerializer(application)

                return Response({
                    'success': True,
                    'message': 'Application submitted successfully',
                    'data': response_serializer.data
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Application submission failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error creating application',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def retrieve(self, request, *args, **kwargs):
        """Retrieve a specific application"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)

            return Response({
                'success': True,
                'message': 'Application retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Application not found',
                'error': str(e)
            }, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def update_status(self, request, pk=None):
        """
        Update application status (Staff/Admin only)
        """
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                'success': False,
                'message': 'You do not have permission to update application status'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            application = self.get_object()
            serializer = ApplicationStatusUpdateSerializer(
                application,
                data=request.data,
                partial=True
            )

            if serializer.is_valid():
                with transaction.atomic():
                    updated_application = serializer.save()

                # Return updated application data
                response_serializer = ApplicationDetailSerializer(updated_application)

                return Response({
                    'success': True,
                    'message': f'Application status updated to {updated_application.get_status_display()}',
                    'data': response_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Status update failed',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error updating application status',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def my_applications(self, request):
        """Get current user's applications"""
        try:
            queryset = self.get_queryset().filter(user=request.user)
            queryset = self.filter_queryset(queryset)

            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)

            return Response({
                'success': True,
                'message': 'Your applications retrieved successfully',
                'data': serializer.data,
                'total_count': queryset.count()
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving your applications',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def statistics(self, request):
        """Get application statistics (Staff/Admin only)"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                'success': False,
                'message': 'You do not have permission to view statistics'
            }, status=status.HTTP_403_FORBIDDEN)

        try:
            total = Application.objects.count()
            pending = Application.objects.filter(status='pending').count()
            in_progress = Application.objects.filter(status='in_progress').count()
            accepted = Application.objects.filter(status='accepted').count()
            rejected = Application.objects.filter(status='rejected').count()

            stats = {
                'total': total,
                'pending': pending,
                'in_progress': in_progress,
                'accepted': accepted,
                'rejected': rejected,
                'completion_rate': round((accepted / total * 100), 2) if total > 0 else 0
            }

            return Response({
                'success': True,
                'message': 'Statistics retrieved successfully',
                'data': stats
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'success': False,
                'message': 'Error retrieving statistics',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)