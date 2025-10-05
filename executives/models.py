from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from accounts.managers import ExecutiveManager
import uuid
from datetime import timedelta


class Language(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Executive(AbstractBaseUser, PermissionsMixin):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

    executive_id = models.CharField(max_length=20, unique=True)
    mobile_number = models.CharField(max_length=15, unique=True)
    name = models.CharField(max_length=100, default="Guest")
    age = models.PositiveIntegerField(default=18)
    email_id = models.EmailField(null=True, blank=True)
    gender = models.CharField(max_length=20, default="unspecified")
    profession = models.CharField(max_length=100, default="Not Provided")
    skills = models.TextField(blank=True)
    place = models.CharField(max_length=100, blank=True)
    education_qualification = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    on_call = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, null=True, blank=True)
    online = models.BooleanField(default=False)
    languages_known = models.ManyToManyField('Language', related_name="executives", blank=True)
    is_verified = models.BooleanField(default=False)
    is_online = models.BooleanField(default=False)
    is_offline = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    is_banned = models.BooleanField(default=False)
    is_logged_out = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    device_id = models.CharField(max_length=255, default=uuid.uuid4)
    last_login = models.DateTimeField(null=True, blank=True)

    manager_executive = models.ForeignKey( 'accounts.Admin', on_delete=models.SET_NULL, null=True, related_name="managed_executives" )

    account_number = models.CharField(max_length=30, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    is_favourite = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = ExecutiveManager()

    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return f"{self.name} ({self.executive_id})"



class ExecutiveStats(models.Model):
    executive = models.OneToOneField(
        Executive, on_delete=models.CASCADE, related_name="stats"
    )
    coins_per_second = models.FloatField(default=3) #from user 
    amount_per_min = models.DecimalField(max_digits=10, decimal_places=2, default=0.0) 
    vault_Balance = models.IntegerField(default=0)

    # Call tracking
    total_on_duty_seconds = models.PositiveIntegerField(default=0)
    total_talk_seconds_today = models.PositiveIntegerField(default=0)
    total_picked_calls = models.PositiveIntegerField(default=0)
    total_missed_calls = models.PositiveIntegerField(default=0)

    total_earnings = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Total lifetime earnings of executive"
    )
    earnings_today = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Earnings for today"
    )
    pending_payout = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Balance to be paid to executive"
    )

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stats for {self.executive.name}"



class ExecutiveToken(models.Model):
    executive = models.ForeignKey('executives.Executive', on_delete=models.CASCADE)
    access_token = models.CharField(max_length=255, unique=True,default='000') 
    refresh_token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField() 


    @classmethod
    def generate(cls, executive):
        access_token = uuid.uuid4().hex
        refresh_token = uuid.uuid4().hex
        expires_at = timezone.now() + timedelta(days=300)
        return cls.objects.create(
            executive=executive,
            access_token=access_token,
            refresh_token=refresh_token,
            revoked=False,
            expires_at=expires_at
        )


class BlockedusersByExecutive(models.Model):
    user = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE, related_name='blocked_users')
    executive = models.ForeignKey(Executive, on_delete=models.CASCADE, related_name='blocked_executives')
    is_blocked = models.BooleanField(default=False)
    reason = models.TextField()
    blocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'executive')

    def __str__(self):
        return f"{self.user.user_id} blocked {self.executive.executive_id}"
    

class ExecutiveProfilePicture(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    executive = models.OneToOneField(Executive, on_delete=models.CASCADE)
    profile_photo = models.ImageField(upload_to='executive_pictures/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def approve(self):
        self.status = 'approved'
        self.save()

    def reject(self):
        self.status = 'rejected'
        self.save()


