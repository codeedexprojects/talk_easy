from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.db import transaction


class UserProfile(models.Model):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    dp_image = models.ImageField(upload_to='user/dp_images/', blank=True, null=True)
    otp = models.CharField(max_length=6, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    gender = models.CharField(max_length=8, choices=GENDER_CHOICES, blank=True, null=True)
    coin_balance = models.PositiveIntegerField(default=0)
    user_id = models.CharField(max_length=10, unique=True, editable=False)
    last_login = models.DateTimeField(null=True, blank=True)
    is_banned = models.BooleanField(default=False)
    is_loginned = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    is_dormant = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name or self.mobile_number or "Unknown User"
    
class UserStats(models.Model):
    user = models.OneToOneField(
        'UserProfile',  
        on_delete=models.CASCADE,
        related_name='stats'
    )
    
    coin_balance = models.PositiveIntegerField(default=0)
    total_calls = models.PositiveIntegerField(default=0)
    total_call_seconds = models.PositiveIntegerField(default=0)
    total_call_seconds_today = models.PositiveIntegerField(default=0)
    
    last_updated = models.DateTimeField(auto_now=True)

    def reset_daily_stats(self):
        self.total_call_seconds_today = 0
        self.save(update_fields=['total_call_seconds_today'])

    def __str__(self):
        return f"Stats for {self.user}"