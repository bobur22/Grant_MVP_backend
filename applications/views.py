# views.py
import os
import uuid

from django.core.files.storage import default_storage
from django_filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, generics, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
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
    CertificateUploadSerializer, RewardListSerializer, RewardCreateUpdateSerializer, RewardDetailSerializer
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
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    filterset_fields = ['created_at']
    ordering_fields = ['name', 'created_at', 'applications_count']
    ordering = ['-created_at']

    def get_queryset(self):
        """Get queryset with annotations"""
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
        """List all rewards with search and filter"""
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response({
                'success': True,
                'rewards': serializer.data
            })

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
    def applications(self, request, pk=None):
        """Get applications for specific reward"""
        reward = self.get_object()
        applications = reward.applications.all()

        # Filter by status if provided
        status_filter = request.query_params.get('status', None)
        if status_filter:
            applications = applications.filter(status=status_filter)

        # Paginate results
        page = self.paginate_queryset(applications)
        if page is not None:
            serializer = ApplicationDetailSerializer(page, many=True)
            return self.get_paginated_response({
                'success': True,
                'applications': serializer.data
            })

        serializer = ApplicationDetailSerializer(applications, many=True)
        return Response({
            'success': True,
            'reward_name': reward.name,
            'applications': serializer.data,
            'count': applications.count()
        })

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
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

# class ApplicationFinalReviewView(MultiStepApplicationMixin, APIView):
#     """
#     Step 4: Final Review and Submit
#     GET: Show all collected data for review
#     POST: Submit final application
#     """
#     permission_classes = [IsAuthenticated]
#
#     def get(self, request):
#         """Get complete application data for final review"""
#         session_data = self.get_session_data(request)
#
#         # Check if all steps are completed
#         required_steps = ['step1_data', 'step2_data', 'step3_data']
#         missing_steps = [step for step in required_steps if step not in session_data]
#
#         if missing_steps:
#             return Response({
#                 'success': False,
#                 'message': 'Barcha qadamlar yakunlanmagan',
#                 'missing_steps': missing_steps
#             }, status=status.HTTP_400_BAD_REQUEST)
#
#         # Combine all data
#         complete_data = {}
#         complete_data.update(session_data.get('step1_data', {}))
#         complete_data.update(session_data.get('step2_data', {}))
#         complete_data.update(session_data.get('step3_data', {}))
#         complete_data['reward_id'] = session_data.get('reward_id')
#
#         # Get reward information
#         try:
#             reward = Reward.objects.get(id=complete_data['reward_id'])
#             complete_data['reward_name'] = reward.name
#         except Reward.DoesNotExist:
#             pass
#
#         return Response({
#             'success': True,
#             'data': complete_data,
#             'current_step': 4
#         })
#
#     def post(self, request):
#         """Submit final application"""
#         session_data = self.get_session_data(request)
#
#         # Check if all steps are completed
#         required_steps = ['step1_data', 'step2_data', 'step3_data']
#         for step in required_steps:
#             if step not in session_data:
#                 return Response({
#                     'success': False,
#                     'message': f'{step} yakunlanmagan'
#                 }, status=status.HTTP_400_BAD_REQUEST)
#
#         # Combine all data
#         final_data = {}
#         final_data.update(session_data.get('step1_data', {}))
#         final_data.update(session_data.get('step2_data', {}))
#         final_data.update(session_data.get('step3_data', {}))
#         final_data['reward_id'] = session_data.get('reward_id')
#         final_data['source'] = 'web'
#
#         # Create final application
#         serializer = ApplicationFinalSerializer(
#             data=final_data,
#             context={'request': request}
#         )
#
#         if serializer.is_valid():
#             try:
#                 application = serializer.create(serializer.validated_data)
#
#                 # Clear session data after successful submission
#                 cache.delete(self.get_session_key(request))
#                 if 'application_reward_id' in request.session:
#                     del request.session['application_reward_id']
#
#                 # Return created application data
#                 response_serializer = ApplicationDetailSerializer(application)
#
#                 return Response({
#                     'success': True,
#                     'message': 'Ariza muvaffaqiyatli yuborildi',
#                     'application': response_serializer.data
#                 }, status=status.HTTP_201_CREATED)
#
#             except Exception as e:
#                 return Response({
#                     'success': False,
#                     'message': f'Ariza saqlashda xatolik: {str(e)}'
#                 }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
#
#         return Response({
#             'success': False,
#             'errors': serializer.errors
#         }, status=status.HTTP_400_BAD_REQUEST)


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


class ApplicationDebugView(MultiStepApplicationMixin, APIView):
    """Debug view to check session data"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get all session data for debugging"""
        session_key = self.get_session_key(request)
        cache_data = cache.get(session_key, {})
        django_session_data = request.session.get(f'app_draft_{request.user.id}', {})

        return Response({
            'success': True,
            'debug_info': {
                'user_id': request.user.id,
                'session_key': session_key,
                'reward_id_in_session': request.session.get('application_reward_id'),
                'cache_data': cache_data,
                'django_session_data': django_session_data,
                'cache_has_data': bool(cache_data),
                'session_has_data': bool(django_session_data),
                'all_session_keys': list(request.session.keys()),
            }
        })


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
