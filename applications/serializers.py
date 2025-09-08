from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Reward, File, Application

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
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Rasm hajmi 5MB dan oshmasligi kerak")

            # Check file type
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
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
        read_only_fields = ['id','email', 'first_name', 'last_name', ]


# serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Application, Reward, Certificates

User = get_user_model()


class ApplicationStep1Serializer(serializers.Serializer):
    """
    Step 1: Personal Information (Shaxsiy ma'lumotlar)
    Fields: F.I.SH, JSHSHIR, Hudud, Tuman, Mahalla, Telefon raqam
    """
    # These fields come from User model
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    jshshir = serializers.CharField(max_length=14, min_length=14)
    phone_number = serializers.CharField(max_length=20)

    # These fields come from Application model
    area = serializers.ChoiceField(choices=Application.AREA_CHOICES)
    district = serializers.CharField(max_length=200)
    neighborhood = serializers.CharField(max_length=200)

    def validate_jshshir(self, value):
        """Validate JSHSHIR format"""
        if not value.isdigit():
            raise serializers.ValidationError("JSHSHIR faqat raqamlardan iborat bo'lishi kerak")
        return value

    def validate_phone_number(self, value):
        """Validate phone number format"""
        # Remove any spaces or special characters
        clean_number = ''.join(filter(str.isdigit, value))
        if len(clean_number) < 9:
            raise serializers.ValidationError("Telefon raqam noto'g'ri formatda")
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
        if len(value.strip()) < 50:
            raise serializers.ValidationError(
                "Faoliyat haqida kamida 50 ta belgi kiriting"
            )
        return value.strip()


class CertificateUploadSerializer(serializers.Serializer):
    """Serializer for certificate file uploads"""
    file = serializers.FileField()

    def validate_file(self, value):
        """Validate certificate file"""
        # Check file size (max 10MB)
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Fayl hajmi 10MB dan oshmasligi kerak")

        # Check file extension
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
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Tavsiya xati hajmi 5MB dan oshmasligi kerak")

            # Check file extension
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
                # Check file size (max 5MB each)
                if certificate.size > 5 * 1024 * 1024:
                    raise serializers.ValidationError(
                        f"Sertifikat fayli '{certificate.name}' hajmi 5MB dan oshmasligi kerak"
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
    jshshir = serializers.CharField(max_length=14)
    phone_number = serializers.CharField(max_length=20)
    area = serializers.ChoiceField(choices=Application.AREA_CHOICES)
    district = serializers.CharField(max_length=200)
    neighborhood = serializers.CharField(max_length=200)

    # Step 2 data
    activity = serializers.CharField(max_length=200)
    activity_description = serializers.CharField()

    # Step 3 data
    recommendation_letter = serializers.FileField(required=False, allow_null=True)
    certificates = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        allow_empty=True
    )

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
        user.jshshir = validated_data['jshshir']
        user.phone_number = validated_data['phone_number']
        user.save()

        # Extract certificates and recommendation letter
        certificates_data = validated_data.pop('certificates', [])
        recommendation_letter = validated_data.pop('recommendation_letter', None)
        reward_id = validated_data.pop('reward_id')

        # Create application
        application = Application.objects.create(
            user=user,
            reward_id=reward_id,
            area=validated_data['area'],
            district=validated_data['district'],
            neighborhood=validated_data['neighborhood'],
            activity=validated_data['activity'],
            activity_description=validated_data['activity_description'],
            recommendation_letter=recommendation_letter,
            source=validated_data.get('source', 'web'),
            status='yuborilgan'
        )

        # Create certificates
        for certificate_file in certificates_data:
            Certificates.objects.create(
                application=application,
                file=certificate_file
            )

        return application


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Serializer for displaying complete application details"""
    user_full_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_jshshir = serializers.CharField(source='user.jshshir', read_only=True)
    user_phone = serializers.CharField(source='user.phone_number', read_only=True)
    reward_name = serializers.CharField(source='reward.name', read_only=True)
    certificates = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    area_display = serializers.CharField(source='get_area_display', read_only=True)

    class Meta:
        model = Application
        fields = [
            'id', 'user_full_name', 'user_jshshir', 'user_phone',
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


# Session-based serializers for temporary storage
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