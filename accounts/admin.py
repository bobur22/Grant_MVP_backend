from django.contrib import admin

from accounts.models import CustomUser, PhoneVerification

admin.site.register(CustomUser)
admin.site.register(PhoneVerification)
