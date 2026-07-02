from django.conf import settings
from django.db import models


class Notification(models.Model):
    AUDIENCE_CHOICES = (
        ('all', 'All (Users + Executives)'),
        ('users', 'Users only'),
        ('executives', 'Executives only'),
    )

    title = models.CharField(max_length=255)
    body = models.TextField()
    image = models.ImageField(upload_to='notifications/', blank=True, null=True)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES)

    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
    )

    total_recipients = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.audience})"
