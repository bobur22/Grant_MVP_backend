from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Reward, File, Application

CustomUser = get_user_model()


class RewardSerializer(serializers.ModelSerializer):
    """Serializer for Reward model"""

    class Meta:
        model = Reward
        fields = ['id', 'name', 'description', 'image', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


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




class ApplicationListSerializer(serializers.ModelSerializer):
    """Serializer for listing applications"""
    reward = RewardSerializer(read_only=True)
    user = CustomUserSerializer(read_only=True)
    files = FileSerializer(many=True, read_only=True, source='file_set')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    files_count = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'reward', 'user', 'files', 'files_count', 'status', 'status_display',
            'source', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_files_count(self, obj):
        return obj.file_set.count()


class ApplicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating applications"""
    files = serializers.ListField(
        child=serializers.FileField(),
        write_only=True,
        required=True,
        allow_empty=False,
        help_text="List of files to upload with the application"
    )

    class Meta:
        model = Application
        fields = ['reward', 'source', 'files']

    def validate_reward(self, value):
        """Validate that reward exists"""
        if not value:
            raise serializers.ValidationError("Reward is required.")
        return value

    def validate_source(self, value):
        """Validate source field"""
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Source must be at least 3 characters long.")
        return value.strip()

    def validate_files(self, value):
        """Validate files"""
        if not value:
            raise serializers.ValidationError("At least one file is required.")

        # Check file count limit
        if len(value) > 5:
            raise serializers.ValidationError("Maximum 5 files allowed per application.")

        # Check file size (optional - adjust as needed)
        max_file_size = 10 * 1024 * 1024  # 10MB
        for file in value:
            if file.size > max_file_size:
                raise serializers.ValidationError(f"File {file.name} is too large. Maximum size is 10MB.")

        return value

    def create(self, validated_data):
        """Create application with files"""
        files_data = validated_data.pop('files')
        user = self.context['request'].user

        # Create application
        application = Application.objects.create(
            user=user,
            reward=validated_data['reward'],
            source=validated_data['source']
        )

        # Create associated files
        for file_data in files_data:
            File.objects.create(
                file=file_data,
                application=application
            )

        return application


class ApplicationDetailSerializer(serializers.ModelSerializer):
    """Serializer for detailed application view"""
    reward = RewardSerializer(read_only=True)
    user = CustomUserSerializer(read_only=True)
    files = FileSerializer(many=True, read_only=True, source='file_set')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    files_count = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            'id', 'reward', 'user', 'files', 'files_count', 'status', 'status_display',
            'source', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reward', 'user', 'files', 'created_at', 'updated_at']

    def get_files_count(self, obj):
        return obj.file_set.count()


class ApplicationStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating application status (admin/staff only)"""

    class Meta:
        model = Application
        fields = ['status']

    def validate_status(self, value):
        """Validate status transition"""
        # valid_statuses = ['yuborilgan', 'in_progress', 'accepted', 'rejected']
        valid_statuses = ['yuborilgan']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Invalid status. Must be one of: {valid_statuses}")
        return value

    def update(self, instance, validated_data):
        """Update only status field"""
        instance.status = validated_data.get('status', instance.status)
        instance.save(update_fields=['status', 'updated_at'])
        return instance