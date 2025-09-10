# views.py
import os
import uuid

from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django_filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, generics, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache
from rest_framework.decorators import action
from .models import Application, Reward, Certificates
from .serializers import (
    ApplicationStep1Serializer,
    ApplicationStep2Serializer,
    ApplicationStep3Serializer,
    ApplicationFinalSerializer,
    ApplicationDetailSerializer,
    ApplicationSessionSerializer,
    CertificateUploadSerializer, RewardListSerializer, RewardCreateUpdateSerializer, RewardDetailSerializer,
    ApplicationListSerializer, ApplicationCreateSerializer
)
from django.db.models import Q, Count
from .permissions import RewardPermission


class RewardViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Reward model with role-based permissions

    Regular users: GET (list, retrieve)
    Admin/Staff: Full CRUD operations
    """
    permission_classes = [RewardPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    search_fields = ['name', 'description']
    filterset_fields = ['created_at']
    ordering_fields = ['name', 'created_at', 'applications_count']
    ordering = ['-created_at']

    def get_queryset(self):
        queryset = Reward.objects.annotate(
            applications_count=Count('applications'),
            pending_applications=Count(
                'applications',
                filter=Q(applications__status__in=['yuborilgan', 'mahalla', 'tuman', 'hudud'])
            ),
            approved_applications=Count(
                'applications',
                filter=Q(applications__status='mukofotlangan')
            )
        )
        return queryset

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'list':
            return RewardListSerializer
        elif self.action == 'retrieve':
            return RewardDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return RewardCreateUpdateSerializer
        else:
            return RewardDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            response = self.get_paginated_response(serializer.data)
            response.data.update({
                'success': True,
            })
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'success': True,
            'rewards': serializer.data,
            'count': queryset.count()
        })

    def retrieve(self, request, *args, **kwargs):
        """Retrieve single reward with detailed info"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)

        return Response({
            'success': True,
            'reward': serializer.data
        })

    def create(self, request, *args, **kwargs):
        """Create new reward (Admin/Staff only)"""
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            reward = serializer.save()

            # Return detailed data
            detail_serializer = RewardDetailSerializer(
                reward,
                context={'request': request}
            )

            return Response({
                'success': True,
                'message': 'Mukofot muvaffaqiyatli yaratildi',
                'reward': detail_serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        """Update reward (Admin/Staff only)"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            reward = serializer.save()

            # Return detailed data
            detail_serializer = RewardDetailSerializer(
                reward,
                context={'request': request}
            )

            return Response({
                'success': True,
                'message': 'Mukofot muvaffaqiyatli yangilandi',
                'reward': detail_serializer.data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Delete reward (Admin/Staff only)"""
        instance = self.get_object()

        # Check if reward has applications
        applications_count = instance.applications.count()
        if applications_count > 0:
            return Response({
                'success': False,
                'message': f'Bu mukofotga {applications_count} ta ariza bog\'langan. O\'chirib bo\'lmaydi.'
            }, status=status.HTTP_400_BAD_REQUEST)

        reward_name = instance.name
        instance.delete()

        return Response({
            'success': True,
            'message': f'"{reward_name}" mukofoti o\'chirildi'
        }, status=status.HTTP_204_NO_CONTENT)
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get detailed statistics for a reward (Admin/Staff only)"""
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                'success': False,
                'message': 'Ruxsat yo\'q'
            }, status=status.HTTP_403_FORBIDDEN)

        reward = self.get_object()
        applications = reward.applications.all()

        stats = {
            'total_applications': applications.count(),
            'status_breakdown': {},
            'monthly_applications': [],
        }

        # Status breakdown
        for status_code, status_name in Application.STATUS_CHOICES:
            count = applications.filter(status=status_code).count()
            stats['status_breakdown'][status_code] = {
                'name': status_name,
                'count': count
            }

        # Monthly applications (last 12 months)
        from django.utils import timezone
        from dateutil.relativedelta import relativedelta

        end_date = timezone.now()
        start_date = end_date - relativedelta(months=12)

        # This is a simplified version - you might want to use Django's aggregation
        monthly_data = []
        current_date = start_date

        while current_date <= end_date:
            month_start = current_date.replace(day=1)
            next_month = month_start + relativedelta(months=1)

            count = applications.filter(
                created_at__gte=month_start,
                created_at__lt=next_month
            ).count()

            monthly_data.append({
                'month': month_start.strftime('%Y-%m'),
                'count': count
            })

            current_date = next_month

        stats['monthly_applications'] = monthly_data

        return Response({
            'success': True,
            'reward_name': reward.name,
            'statistics': stats
        })


class MultiStepApplicationMixin:
    """Mixin for handling session-based multi-step forms"""

    def get_session_key(self, request):
        """Generate unique session key for application"""
        user_id = request.user.id
        # Try to get reward_id from multiple sources
        reward_id = (
                request.data.get('reward_id') or
                request.GET.get('reward_id') or
                request.session.get('application_reward_id')
        )

        # If no reward_id found, use a default session key
        if not reward_id:
            return f"application_draft_{user_id}"

        return f"application_draft_{user_id}_{reward_id}"

    def get_session_data(self, request):
        """Get application data from session/cache"""
        session_key = self.get_session_key(request)
        return cache.get(session_key, {})

    def save_session_data(self, request, data, step=None):
        """Save application data to session/cache"""
        session_key = self.get_session_key(request)
        session_data = self.get_session_data(request)

        if step:
            session_data[f'step{step}_data'] = data
            session_data['current_step'] = step
        else:
            session_data.update(data)

        # Save reward_id in session for consistency
        if 'reward_id' in data:
            request.session['application_reward_id'] = data['reward_id']
            session_data['reward_id'] = data['reward_id']

        # Cache for 1 hour
        cache.set(session_key, session_data, 3600)
        return session_data


class ApplicationStep1View(MultiStepApplicationMixin, APIView):
    """
    Step 1: Personal Information
    POST: Save personal info and move to step 2
    GET: Retrieve current step 1 data
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current step 1 data"""
        session_data = self.get_session_data(request)
        step1_data = session_data.get('step1_data', {})

        # Pre-fill with user data if available
        if not step1_data and request.user:
            step1_data = {
                'first_name': request.user.first_name or '',
                'last_name': request.user.last_name or '',
                'jshshir': getattr(request.user, 'jshshir', '') or '',
                'phone_number': getattr(request.user, 'phone_number', '') or '',
                'area': '',
                'district': '',
                'neighborhood': ''
            }

        return Response({
            'success': True,
            'data': step1_data,
            'current_step': 1
        })

    def post(self, request):
        """Save step 1 data and proceed to step 2"""
        serializer = ApplicationStep1Serializer(data=request.data)

        if serializer.is_valid():
            # Check if user already has application for this reward
            reward_id = serializer.validated_data['reward_id']
            existing_application = Application.objects.filter(
                user=request.user,
                reward_id=reward_id
            ).first()

            if existing_application:
                return Response({
                    'success': False,
                    'message': 'Siz ushbu mukofot uchun allaqachon ariza topshirgansiz',
                    'existing_application_id': existing_application.id,
                    'existing_application_status': existing_application.status
                }, status=status.HTTP_400_BAD_REQUEST)

            # Save to session
            session_data = self.save_session_data(
                request,
                serializer.validated_data,
                step=1
            )

            return Response({
                'success': True,
                'message': 'Shaxsiy ma\'lumotlar saqlandi',
                'next_step': 2,
                'data': serializer.validated_data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ApplicationStep2View(MultiStepApplicationMixin, APIView):
    """
    Step 2: Activity Information
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current step 2 data"""
        session_data = self.get_session_data(request)
        step2_data = session_data.get('step2_data', {})

        return Response({
            'success': True,
            'data': step2_data,
            'current_step': 2
        })

    def post(self, request):
        """Save step 2 data and proceed to step 3"""
        # Check if step 1 is completed
        session_data = self.get_session_data(request)
        if 'step1_data' not in session_data:
            return Response({
                'success': False,
                'message': 'Avval 1-qadamni yakunlang'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApplicationStep2Serializer(data=request.data)

        if serializer.is_valid():
            # Save to session
            self.save_session_data(
                request,
                serializer.validated_data,
                step=2
            )

            return Response({
                'success': True,
                'message': 'Faoliyat ma\'lumotlari saqlandi',
                'next_step': 3,
                'data': serializer.validated_data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ApplicationStep3View(MultiStepApplicationMixin, APIView):
    """
    Step 3: Document Upload
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current step 3 data"""
        session_data = self.get_session_data(request)
        step3_data = session_data.get('step3_data', {})

        return Response({
            'success': True,
            'data': step3_data,
            'current_step': 3
        })

    def post(self, request):
        """Save step 3 data and proceed to final review"""
        # Check if previous steps are completed
        session_data = self.get_session_data(request)
        if 'step1_data' not in session_data or 'step2_data' not in session_data:
            return Response({
                'success': False,
                'message': 'Avval oldingi qadamlarni yakunlang'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApplicationStep3Serializer(data=request.data)

        if serializer.is_valid():
            validated_data = serializer.validated_data.copy()

            # Prepare data for session storage (JSON serializable)
            session_data = {}

            # Handle recommendation letter file
            if 'recommendation_letter' in validated_data and validated_data['recommendation_letter']:
                rec_file = validated_data['recommendation_letter']

                # Generate unique filename
                file_extension = os.path.splitext(rec_file.name)[1]
                unique_filename = f"temp_rec_{uuid.uuid4()}{file_extension}"

                # Save file temporarily
                file_path = default_storage.save(
                    f"temp_uploads/{unique_filename}",
                    rec_file
                )

                session_data['recommendation_letter'] = {
                    'original_name': rec_file.name,
                    'file_path': file_path,
                    'file_size': rec_file.size
                }

            # Handle certificates
            if 'certificates' in validated_data and validated_data['certificates']:
                certificates_data = []

                for cert_file in validated_data['certificates']:
                    # Generate unique filename
                    file_extension = os.path.splitext(cert_file.name)[1]
                    unique_filename = f"temp_cert_{uuid.uuid4()}{file_extension}"

                    # Save file temporarily
                    file_path = default_storage.save(
                        f"temp_uploads/{unique_filename}",
                        cert_file
                    )

                    certificates_data.append({
                        'original_name': cert_file.name,
                        'file_path': file_path,
                        'file_size': cert_file.size
                    })

                session_data['certificates'] = certificates_data

            # Save to session (now JSON serializable)
            self.save_session_data(request, session_data, step=3)

            # Prepare response data
            response_data = {}
            if 'recommendation_letter' in session_data:
                response_data['recommendation_letter'] = session_data['recommendation_letter']['original_name']

            if 'certificates' in session_data:
                response_data['certificates_count'] = len(session_data['certificates'])
                response_data['certificates_names'] = [
                    cert['original_name'] for cert in session_data['certificates']
                ]

            return Response({
                'success': True,
                'message': 'Hujjatlar saqlandi',
                'next_step': 4,  # Final review step
                'data': response_data
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ApplicationFinalReviewView(MultiStepApplicationMixin, APIView):
    """
    Step 4: Final Review and Submit
    GET: Show all collected data for review
    POST: Submit final application
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get complete application data for final review"""
        session_data = self.get_session_data(request)

        # Check if all steps are completed
        required_steps = ['step1_data', 'step2_data', 'step3_data']
        missing_steps = [step for step in required_steps if step not in session_data]

        if missing_steps:
            return Response({
                'success': False,
                'message': 'Barcha qadamlar yakunlanmagan',
                'missing_steps': missing_steps
            }, status=status.HTTP_400_BAD_REQUEST)

        # Combine all data for review
        complete_data = {}
        complete_data.update(session_data.get('step1_data', {}))
        complete_data.update(session_data.get('step2_data', {}))

        # Handle step3 data (files) for display
        step3_data = session_data.get('step3_data', {})
        if 'recommendation_letter' in step3_data:
            complete_data['recommendation_letter_info'] = step3_data['recommendation_letter']
        if 'certificates' in step3_data:
            complete_data['certificates_info'] = step3_data['certificates']

        complete_data['reward_id'] = session_data.get('reward_id')

        # Get reward information
        try:
            reward = Reward.objects.get(id=complete_data['reward_id'])
            complete_data['reward_name'] = reward.name
        except Reward.DoesNotExist:
            pass

        return Response({
            'success': True,
            'data': complete_data,
            'current_step': 4
        })

    def post(self, request):
        """Submit final application - NO FILE UPLOADS HERE"""
        session_data = self.get_session_data(request)

        # Check if all steps are completed
        required_steps = ['step1_data', 'step2_data', 'step3_data']
        for step in required_steps:
            if step not in session_data:
                return Response({
                    'success': False,
                    'message': f'{step} yakunlanmagan'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Prepare final data from session
        final_data = {}
        reward_id = session_data.get('step1_data', {}).get('reward_id')
        existing_application = Application.objects.filter(
            user=request.user,
            reward_id=reward_id
        ).first()

        if existing_application:
            return Response({
                'success': False,
                'message': 'Siz ushbu mukofot uchun allaqachon ariza topshirgansiz',
                'existing_application': {
                    'id': existing_application.id,
                    'status': existing_application.status,
                    'created_at': existing_application.created_at
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        # Step 1 data
        step1_data = session_data.get('step1_data', {})
        final_data.update({
            'first_name': step1_data.get('first_name'),
            'last_name': step1_data.get('last_name'),
            'pinfl': step1_data.get('pinfl'),
            'phone_number': step1_data.get('phone_number'),
            'area': step1_data.get('area'),
            'district': step1_data.get('district'),
            'neighborhood': step1_data.get('neighborhood'),
            'reward_id': step1_data.get('reward_id')
        })

        # Step 2 data
        step2_data = session_data.get('step2_data', {})
        final_data.update({
            'activity': step2_data.get('activity'),
            'activity_description': step2_data.get('activity_description')
        })

        # Step 3 data (file metadata)
        step3_data = session_data.get('step3_data', {})
        final_data.update({
            'recommendation_letter': step3_data.get('recommendation_letter'),
            'certificates': step3_data.get('certificates', [])
        })

        final_data['source'] = 'web'

        # Create final application using the fixed serializer
        serializer = ApplicationFinalSerializer(
            data=final_data,
            context={'request': request}
        )

        if serializer.is_valid():
            try:
                application = serializer.create(serializer.validated_data)

                # Clear session data after successful submission
                cache.delete(self.get_session_key(request))
                if 'application_reward_id' in request.session:
                    del request.session['application_reward_id']

                # Return created application data
                response_serializer = ApplicationDetailSerializer(application)

                return Response({
                    'success': True,
                    'message': 'Ariza muvaffaqiyatli yuborildi',
                    'application': response_serializer.data
                }, status=status.HTTP_201_CREATED)

            except Exception as e:
                return Response({
                    'success': False,
                    'message': f'Ariza saqlashda xatolik: {str(e)}'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)

class ApplicationStatusView(MultiStepApplicationMixin, APIView):
    """Get current application progress status"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get current progress status"""
        session_data = self.get_session_data(request)

        progress = {
            'step1_completed': 'step1_data' in session_data,
            'step2_completed': 'step2_data' in session_data,
            'step3_completed': 'step3_data' in session_data,
            'current_step': session_data.get('current_step', 1),
            'reward_id': session_data.get('reward_id'),
        }

        return Response({
            'success': True,
            'progress': progress
        })


class CertificateUploadView(APIView):
    """Handle individual certificate uploads"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Upload a single certificate file"""
        serializer = CertificateUploadSerializer(data=request.data)

        if serializer.is_valid():
            # Handle file upload temporarily
            # In production, save to temporary storage
            uploaded_file = serializer.validated_data['file']

            return Response({
                'success': True,
                'message': 'Fayl yuklandi',
                'file_info': {
                    'name': uploaded_file.name,
                    'size': uploaded_file.size,
                    'content_type': uploaded_file.content_type
                }
            })

        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class ApplicationCreateView(generics.CreateAPIView):
    """Create new application for a specific reward"""
    serializer_class = ApplicationCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()

        return_serializer = ApplicationDetailSerializer(
            application,
            context={'request': request}
        )
        return Response(
            return_serializer.data,
            status=status.HTTP_201_CREATED
        )


class ApplicationListView(generics.ListAPIView):
    """
    List applications:
    - Admin users see all applications
    - Regular users see only their own applications
    """
    serializer_class = ApplicationListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'area', 'reward']
    ordering = ['-created_at']

    def get_queryset(self):
        if self.request.user.is_staff:
            # Admin users see all applications
            return Application.objects.select_related(
                'user', 'reward'
            ).prefetch_related('certificates_set')
        else:
            # Regular users see only their own applications
            return Application.objects.filter(
                user=self.request.user
            ).select_related(
                'user', 'reward'
            ).prefetch_related('certificates_set')


class MyApplicationsView(generics.ListAPIView):
    """List current user's applications only"""
    serializer_class = ApplicationListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'area', 'reward']
    ordering = ['-created_at']

    def get_queryset(self):
        return Application.objects.filter(
            user=self.request.user
        ).select_related(
            'user', 'reward'
        ).prefetch_related('certificates_set')




class RewardApplicationsView(generics.ListAPIView):
    """Get all applications for a specific reward (Admin only)"""
    serializer_class = ApplicationListSerializer
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'area']
    ordering = ['-created_at']

    def get_queryset(self):
        reward_id = self.kwargs['reward_id']
        return Application.objects.filter(
            reward_id=reward_id
        ).select_related(
            'user', 'reward'
        ).prefetch_related('certificates_set')


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_draft(request):
    """Clear current application draft"""
    reward_id = request.query_params.get('reward_id')
    if reward_id:
        session_key = f"application_draft_{request.user.id}_{reward_id}"
        cache.delete(session_key)

    return Response({
        'success': True,
        'message': 'Ariza loyihasi tozalandi'
    })


class ApplicationsListView(APIView):
    """
    Get applications list with role-based access:
    - Admin/Staff: See all applications
    - Regular users: See only their applications
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get applications list based on user role"""

        # Get query parameters
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        status_filter = request.query_params.get('status')  # Filter by status
        reward_id = request.query_params.get('reward_id')  # Filter by reward
        search = request.query_params.get('search')  # Search by user name or PINFL

        # Base queryset
        if request.user.is_staff or request.user.is_superuser:
            # Admin/Staff can see all applications
            queryset = Application.objects.all()
        else:
            # Regular users see only their applications
            queryset = Application.objects.filter(user=request.user)

        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if reward_id:
            queryset = queryset.filter(reward_id=reward_id)

        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(user__pinfl__icontains=search) |
                Q(reward__name__icontains=search)
            )

        # Order by creation date (newest first)
        queryset = queryset.select_related('user', 'reward').order_by('-created_at')

        # Pagination
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        # Serialize data
        applications_data = []
        for app in page_obj:
            applications_data.append({
                'ariza_raqami': app.id,  # Application ID
                'xizmat_nomi': app.reward.name,  # Reward name
                'yuborilgan_kuni': app.created_at.strftime('%d.%m.%Y'),  # Created date
                'holati': app.get_status_display(),  # Status display
                'holati_code': app.status,  # Status code for frontend logic
                'manba': app.get_source_display() if hasattr(app, 'get_source_display') else app.source,  # Source

                # Additional info (especially useful for admins)
                'foydalanuvchi': f"{app.user.first_name} {app.user.last_name}" if request.user.is_staff else None,
                'pinfl': app.user.pinfl if request.user.is_staff else None,
                'telefon': app.user.phone_number if request.user.is_staff else None,
                'hudud': app.get_area_display() if request.user.is_staff else None,

                # File counts
                'tavsiya_xati': 'Mavjud' if app.recommendation_letter else 'Mavjud emas',
                'sertifikatlar_soni': app.certificates_set.count() if hasattr(app, 'certificates_set') else 0,

                # Timestamps
                'yaratilgan_vaqt': app.created_at.strftime('%d.%m.%Y %H:%M'),
                'yangilangan_vaqt': app.updated_at.strftime('%d.%m.%Y %H:%M') if hasattr(app, 'updated_at') else None,
            })

        return Response({
            'success': True,
            'data': applications_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
                'page_size': page_size
            },
            'filters': {
                'status': status_filter,
                'reward_id': reward_id,
                'search': search
            },
            'user_role': 'admin' if request.user.is_staff else 'user'
        })


class ApplicationDetailView(APIView):
    """
    Get detailed information about a specific application
    - Admin/Staff: Can see any application
    - Regular users: Can see only their own applications
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):
        """Get detailed application information"""
        try:
            if request.user.is_staff or request.user.is_superuser:
                application = Application.objects.select_related('user', 'reward').get(id=application_id)
            else:
                application = Application.objects.select_related('user', 'reward').get(
                    id=application_id,
                    user=request.user
                )
        except Application.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Ariza topilmadi yoki sizga ruxsat berilmagan'
            }, status=status.HTTP_404_NOT_FOUND)


        certificates = []
        if hasattr(application, 'certificates_set'):
            for cert in application.certificates_set.all():
                certificates.append({
                    'id': cert.id,
                    'fayl_nomi': cert.get_filename() if hasattr(cert, 'get_filename') else cert.file.name.split('/')[
                        -1],
                    'fayl_url': cert.file.url if cert.file else None,
                    'yuklangan_vaqt': cert.created_at.strftime('%d.%m.%Y %H:%M') if hasattr(cert,
                                                                                            'created_at') else None
                })

        # Prepare detailed response
        detail_data = {
            'ariza_raqami': application.id,
            'xizmat_nomi': application.reward.name,
            'xizmat_rasmi': application.reward.image.url if application.reward.image else None,
            'holati': application.get_status_display(),
            'holati_code': application.status,
            'manba': application.get_source_display() if hasattr(application,
                                                                 'get_source_display') else application.source,

            # Personal information
            'shaxsiy_malumotlar': {
                'ism': application.user.first_name,
                'familiya': application.user.last_name,
                'pinfl': application.user.pinfl,
                'telefon': application.user.phone_number,
                'hudud': application.get_area_display(),
                'tuman': application.district,
                'mahalla': application.neighborhood,
            },

            # Activity information
            'faoliyat_malumotlari': {
                'faoliyat_sohasi': application.activity,
                'faoliyat_haqida': application.activity_description,
            },

            # Documents
            'hujjatlar': {
                'tavsiya_xati': {
                    'mavjud': bool(application.recommendation_letter),
                    'fayl_url': application.recommendation_letter.url if application.recommendation_letter else None,
                    'fayl_nomi': application.recommendation_letter.name.split('/')[
                        -1] if application.recommendation_letter else None
                },
                'sertifikatlar': certificates
            },

            # Timestamps
            'vaqtlar': {
                'yuborilgan': application.created_at.strftime('%d.%m.%Y %H:%M'),
                'yangilangan': application.updated_at.strftime('%d.%m.%Y %H:%M') if hasattr(application,
                                                                                            'updated_at') else None
            }
        }

        return Response({
            'success': True,
            'data': detail_data
        })



class ApplicationStatsView(APIView):
    """
    Get application statistics (for admin dashboard)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get application statistics"""

        if not (request.user.is_staff or request.user.is_superuser):
            return Response({
                'success': False,
                'message': 'Bu ma\'lumotlarga faqat administratorlar kirishi mumkin'
            }, status=status.HTTP_403_FORBIDDEN)

        # Get statistics
        from django.db.models import Count

        total_applications = Application.objects.count()

        # Status breakdown
        status_stats = Application.objects.values('status').annotate(count=Count('status'))
        status_breakdown = {stat['status']: stat['count'] for stat in status_stats}

        # Source breakdown
        source_stats = Application.objects.values('source').annotate(count=Count('source'))
        source_breakdown = {stat['source']: stat['count'] for stat in source_stats}

        # Recent applications (last 7 days)
        from datetime import datetime, timedelta
        recent_date = datetime.now() - timedelta(days=7)
        recent_applications = Application.objects.filter(created_at__gte=recent_date).count()

        # Top rewards by application count
        reward_stats = Application.objects.values('reward__name').annotate(
            count=Count('reward')
        ).order_by('-count')[:5]

        return Response({
            'success': True,
            'stats': {
                'umumiy_arizalar': total_applications,
                'holat_boyicha': status_breakdown,
                'manba_boyicha': source_breakdown,
                'oxirgi_7_kun': recent_applications,
                'eng_kop_arizalar': list(reward_stats)
            }
        })