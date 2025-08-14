from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
import string, random
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid


class UserProfileOutstandingToken(models.Model):
    # If you have an Admin model, use it; otherwise keep UserProfile
    user = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='outstanding_tokens')
    jti = models.CharField(max_length=255, unique=True)  # JWT ID
    token = models.TextField()  # the actual token string
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'userprofile_outstanding_token'  # Explicitly set table name

    def __str__(self):
        return f'Token for {self.user} - {self.jti}'

class UserProfileBlacklistedToken(models.Model):
    token = models.OneToOneField(
        'UserProfileOutstandingToken', 
        on_delete=models.CASCADE, 
        related_name='blacklisted_token'
    )
    blacklisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'userprofile_blacklisted_token'  # Explicitly set table name

    def __str__(self):
        return f'Blacklisted token {self.token.jti} for {self.token.user}'


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

    PREFIX = "TUR"  

    class Meta:
        db_table = 'userprofile'  # Explicitly set table name

    def __str__(self):
        return self.name or self.mobile_number or "Unknown User"
    
    def generate_unique_user_id(self):
        prefix = self.PREFIX  
        
        with transaction.atomic():
            last_user = UserProfile.objects.filter(
                user_id__startswith=prefix
            ).order_by('-user_id').first()
            
            if last_user and last_user.user_id:
                last_number = int(last_user.user_id[len(prefix):])
                new_number = last_number + 1
            else:
                new_number = 1001  
            
            return f"{prefix}{new_number}"
            
    def save(self, *args, **kwargs):
        if not self.user_id:
            self.user_id = self.generate_unique_user_id()
        super().save(*args, **kwargs)

    @property
    def is_authenticated(self):
        return True
    
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
    

class ReferralCode(models.Model):
    user = models.OneToOneField(
        'UserProfile',  
        on_delete=models.CASCADE,
        related_name='referral_code'
    )
    code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"ReferralCode({self.code}) for {self.user}"
    
@receiver(post_save, sender=UserProfile)
def create_referral_code(sender, instance, created, **kwargs):
    if created:
        code = f"TE{uuid.uuid4().hex[:6].upper()}"
        ReferralCode.objects.create(user=instance, code=code)
    
class ReferralHistory(models.Model):
    referrer = models.ForeignKey('UserProfile', on_delete=models.CASCADE, related_name='referrals_made')
    referred_user = models.OneToOneField('UserProfile',on_delete=models.CASCADE, related_name='referral_info' )
    referred_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.referrer} referred {self.referred_user}"
    
class DeletedUser(models.Model):
    mobile_number = models.CharField(max_length=15, unique=True)
    deleted_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"DeletedUser {self.mobile_number}"

class BlacklistedToken(models.Model):
    token = models.CharField(max_length=500, unique=True)
    blacklisted_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Blacklisted token {self.token[:10]}..."