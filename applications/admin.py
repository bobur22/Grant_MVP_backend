from django.contrib import admin
from applications.models import Application, File, Reward

class ApplicationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'reward', 'status'
    ]
    search_fields = ['id', 'user', 'reward']
    list_display_links = ['id', 'user',]
    list_per_page = 1000


class RewardAdmin(admin.ModelAdmin):
    list_display = ['name', ]

admin.site.register(Application, ApplicationAdmin)
admin.site.register(Reward, RewardAdmin)
admin.site.register(File)