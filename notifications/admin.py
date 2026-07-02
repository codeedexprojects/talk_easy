from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'total_recipients', 'success_count', 'failure_count', 'sent_by', 'created_at')
    list_filter = ('audience', 'created_at')
    readonly_fields = ('total_recipients', 'success_count', 'failure_count', 'created_at')
