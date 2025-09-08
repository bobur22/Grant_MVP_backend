from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Reward, File, Application, Certificates

CustomUser = get_user_model()


class RewardListSerializer(serializers.ModelSerializer):
    """Serializer for listing rewards"""
    applications_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reward
        fields = [
            'id', 'name', 'description', 'image',
            'applications_count', 'created_at'
        ]


class RewardDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for reward with statistics"""
    applications_count = serializers.IntegerField(read_only=True)
    pending_applications = serializers.IntegerField(read_only=True)
    approved_applications = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reward
        fields = [
            'id', 'name', 'description', 'image',
            'applications_count', 'pending_applications', 'approved_applications',
            'created_at', 'updated_at'
        ]


class RewardCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating rewards (Admin only)"""

    class Meta:
        model = Reward
        fields = ['name', 'description', 'image']

    def validate_name(self, value):
        """Validate reward name uniqueness"""
        if self.instance:
            # Update case - exclude current instance
            if Reward.objects.exclude(pk=self.instance.pk).filter(name__iexact=value).exists():
                raise serializers.ValidationError("Bu nomdagi mukofot allaqachon mavjud")
        else:
            # Create case
            if Reward.objects.filter(name__iexact=value).exists():
                raise serializers.ValidationError("Bu nomdagi mukofot allaqachon mavjud")
        return value

    def validate_image(self, value):
        """Validate image file"""
        if value:
            # Check file size (max 5MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("Rasm hajmi 10MB dan oshmasligi kerak")

            # Check file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', ]
            if value.content_type not in allowed_types:
                raise serializers.ValidationError("Faqat JPEG, PNG, WEBP formatdagi rasmlar qabul qilinadi")

        return value


class FileSerializer(serializers.ModelSerializer):
    """Serializer for File model"""
    filename = serializers.SerializerMethodField()

    class Meta:
        model = File
        fields = ['id', 'file', 'filename', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_filename(self, obj):
        return obj.get_filename()


class CustomUserSerializer(serializers.ModelSerializer):
    """Basic user serializer for applications"""

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', ]
        read_only_fields = ['id', 'email', 'first_name', 'last_name', ]


class ApplicationStep1Serializer(serializers.Serializer):
    """
    Step 1: Personal Information (Shaxsiy ma'lumotlar)
    Fields: F.I.SH, JSHSHIR, Hudud, Tuman, Mahalla, Telefon raqam
    """
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    pinfl = serializers.CharField(max_length=14, min_length=14)
    phone_number = serializers.CharField(max_length=20)

    area = serializers.ChoiceField(choices=Application.AREA_CHOICES)
    district = serializers.CharField(max_length=200)
    neighborhood = serializers.CharField(max_length=200)
    reward_id = serializers.IntegerField()

    def validate_pinfl(self, value):
        """Validate PINFL format"""
        if not value.isdigit():
            raise serializers.ValidationError("JSHSHIR faqat raqamlardan iborat bo'lishi kerak")
        return value

    def validate_phone_number(self, value):
        """Validate phone number format"""
        # Remove any spaces or special characters
        clean_number = ''.join(filter(str.isdigit, value))
        if len(clean_number) > 15:
            raise serializers.ValidationError("Telefon raqam noto'g'ri formatda")
        return value

    def validate_reward_id(self, value):
        """Validate reward exists"""
        try:
            Reward.objects.get(id=value)
        except Reward.DoesNotExist:
            raise serializers.ValidationError("Tanlangan mukofot mavjud emas")
        return value


class ApplicationStep2Serializer(serializers.Serializer):
    """
    Step 2: Activity Information (Mukofot yo'nalishi)
    Fields: Faoliyat sohasi, Faoliyat haqida
    """
    activity = serializers.CharField(max_length=200)
    activity_description = serializers.CharField()

    def validate_activity_description(self, value):
        """Validate activity description length"""
        if not value:
            raise serializers.ValidationError(
                "Faoliyat haqida ma'lumot kiritilishi shart"
            )
        if len(value) > 200:
            raise serializers.ValidationError(
                "200 ta belgidan kam malumot kiritilsin"
            )
        return value.strip()


class CertificateUploadSerializer(serializers.Serializer):
    """Serializer for certificate file uploads"""
    file = serializers.FileField()

    def validate_file(self, value):
        """Validate certificate file"""
        if value.size > 15 * 1024 * 1024:  # less than 15mb
            raise serializers.ValidationError("Fayl hajmi 15MB dan oshmasligi kerak")

        allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx']
        if not any(value.name.lower().endswith(ext) for ext in allowed_extensions):
            raise serializers.ValidationError(
                f"Faqat {', '.join(allowed_extensions)} formatdagi fayllar qabul qilinadi"
            )

        return value


class ApplicationStep3Serializer(serializers.Serializer):
    """
    Step 3: Documents Upload (Yutuqlarni tasdiqlash)
    Fields: Tavsiya xati, Sertifikatlar
    """
    recommendation_letter = serializers.FileField(required=False, allow_null=True)
    certificates = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True
    )

    def validate_recommendation_letter(self, value):
        """Validate recommendation letter"""
        if value:
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("Tavsiya xati hajmi 10MB dan oshmasligi kerak")

            allowed_extensions = ['.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png']
            if not any(value.name.lower().endswith(ext) for ext in allowed_extensions):
                raise serializers.ValidationError(
                    f"Tavsiya xati uchun faqat {', '.join(allowed_extensions)} formatdagi fayllar qabul qilinadi"
                )
        return value

    def validate_certificates(self, value):
        """Validate certificates"""
        if value:
            # Check maximum number of files
            if len(value) > 10:
                raise serializers.ValidationError("Maksimal 10 ta sertifikat yuklash mumkin")

            # Validate each certificate
            for certificate in value:
                # Check file size (max 10MB each)
                if certificate.size > 10 * 1024 * 1024:
                    raise serializers.ValidationError(
                        f"Sertifikat fayli '{certificate.name}' hajmi 10MB dan oshmasligi kerak"
                    )

                # Check file extension
                allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx']
                if not any(certificate.name.lower().endswith(ext) for ext in allowed_extensions):
                    raise serializers.ValidationError(
                        f"Sertifikat '{certificate.name}' uchun faqat {', '.join(allowed_extensions)} formatdagi fayllar qabul qilinadi"
                    )

        return value


class ApplicationFinalSerializer(serializers.Serializer):
    """
    Final Step: Complete Application Data for Review
    All data from previous steps combined
    """
    # Step 1 data
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    pinfl = serializers.CharField(max_length=14)
    phone_number = serializers.CharField(max_length=20)
    area = serializers.ChoiceField(choices=Application.AREA_CHOICES)
    district = serializers.CharField(max_length=200)
    neighborhood = serializers.CharField(max_length=200)

    # Step 2 data
    activity = serializers.CharField(max_length=200)
    activity_description = serializers.CharField()

    # Step 3 data - NO VALIDATION, just accept whatever comes from session
    recommendation_letter = serializers.JSONField(required=False, allow_null=True)
    certificates = serializers.JSONField(required=False, default=list)

    # Additional fields
    reward_id = serializers.IntegerField()
    source = serializers.CharField(max_length=200, default="web")

    def validate_reward_id(self, value):
        """Validate reward exists"""
        try:
            Reward.objects.get(id=value)
        except Reward.DoesNotExist:
            raise serializers.ValidationError("Tanlangan mukofot mavjud emas")
        return value

    def create(self, validated_data):
        """Create application with all related data"""
        user = self.context['request'].user

        # Update user information
        user.first_name = validated_data['first_name']
        user.last_name = validated_data['last_name']
        user.pinfl = validated_data['pinfl']
        user.phone_number = validated_data['phone_number']
        user.save()

        # Extract file metadata
        certificates_data = validated_data.pop('certificates', [])
        recommendation_letter_data = validated_data.pop('recommendation_letter', None)
        reward_id = validated_data.pop('reward_id')

        # Handle recommendation letter file
        recommendation_letter_file = None
        if recommendation_letter_data and recommendation_letter_data.get('file_path'):
            from django.core.files.storage import default_storage
            from django.core.files.base import ContentFile

            try:
                # Read file from temporary storage
                file_content = default_storage.open(recommendation_letter_data['file_path']).read()
                recommendation_letter_file = ContentFile(
                    file_content,
                    name=recommendation_letter_data['original_name']
                )
            except Exception as e:
                print(f"Error reading recommendation letter: {e}")

        # Create application
        application = Application.objects.create(
            user=user,
            reward_id=reward_id,
            area=validated_data['area'],
            district=validated_data['district'],
            neighborhood=validated_data['neighborhood'],
            activity=validated_data['activity'],
            activity_description=validated_data['activity_description'],
            recommendation_letter=recommendation_letter_file,
            source=validated_data.get('source', 'web'),
            status='yuborilgan'
        )

        # Create certificates from file metadata
        for cert_data in certificates_data:
            if cert_data.get('file_path'):
                try:
                    # Read file from temporary storage
                    file_content = default_storage.open(cert_data['file_path']).read()
                    certificate_file = ContentFile(
                        file_content,
                        name=cert_data['original_name']
                    )

                    Certificates.objects.create(
                        application=application,
                        file=certificate_file
                    )
                except Exception as e:
                    print(f"Error reading certificate {cert_data['original_name']}: {e}")

        # Clean up temporary files after successful creation
        self._cleanup_temp_files(certificates_data, recommendation_letter_data)

        return application

    def _cleanup_temp_files(self, certificates_data, recommendation_letter_data):
        """Clean up temporary files"""
        from django.core.files.storage import default_storage

        # Clean up recommendation letter
        if recommendation_letter_data and recommendation_letter_data.get('file_path'):
            try:
                default_storage.delete(recommendation_letter_data['file_path'])
            except Exception as e:
                print(f"Error deleting temp file: {e}")

        # Clean up certificates
        for cert_data in certificates_data:
            if cert_data.get('file_path'):
                try:
                    default_storage.delete(cert_data['file_path'])
                except Exception as e:
                    print(f"Error deleting temp file: {e}")


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Serializer for displaying complete application details"""
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_pinfl = serializers.CharField(source='user.pinfl', read_only=True)
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    reward_name = serializers.CharField(source='reward.name', read_only=True)
    certificates = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    area_display = serializers.CharField(source='get_area_display', read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'user_full_name', 'user_pinfl', 'user_phone',
            'reward_name', 'status', 'status_display',
            'area', 'area_display', 'district', 'neighborhood',
            'activity', 'activity_description', 'recommendation_letter',
            'certificates', 'source', 'created_at', 'updated_at'
        ]

    def get_certificates(self, obj):
        """Get certificates list"""
        return [
            {
                'id': cert.id,
                'filename': cert.get_filename(),
                'url': cert.file.url if cert.file else None,
                'created_at': cert.created_at
            }
            for cert in obj.certificates_set.all()
        ]


class ApplicationSessionSerializer(serializers.Serializer):
    """Serializer for session-based application data storage"""
    step1_data = serializers.JSONField(required=False)
    step2_data = serializers.JSONField(required=False)
    step3_data = serializers.JSONField(required=False)
    current_step = serializers.IntegerField(default=1)
    reward_id = serializers.IntegerField()

    def validate_current_step(self, value):
        if value not in [1, 2, 3, 4]:
            raise serializers.ValidationError("Noto'g'ri qadam raqami")
        return value
