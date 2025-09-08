from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CustomUser, PhoneVerification, PasswordResetCode


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'phone_number', 'first_name', 'last_name', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_superuser', 'is_active']
    search_fields = ['email', 'phone_number', 'first_name', 'last_name']
    ordering = ['email']

    fieldsets = (
        (None, {'fields': ('email', 'phone_number', 'password')}),
        ('Personal Info', {
            'fields': (
                'first_name', 'last_name', 'other_name', 'birth_date',
                'address', 'gender', 'passport_number', 'pinfl', 'profile_picture'
            )
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser')
        }),
        ('Important Dates', {
            'fields': ('last_login', 'created_at', 'updated_at')
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'phone_number', 'first_name', 'last_name', 'other_name',
                'gender', 'password1', 'password2', 'is_staff', 'is_superuser',
            ),
        }),
    )

    readonly_fields = ('last_login', 'created_at', 'updated_at')


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(PhoneVerification)
admin.site.register(PasswordResetCode)