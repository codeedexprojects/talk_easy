from django.db import models
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from accounts.managers import ExecutiveManager
import uuid
from datetime import timedelta
from decimal import Decimal
import json


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
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)
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
    fcm_token = models.CharField(max_length=500, blank=True, null=True)

    manager_executive = models.ForeignKey( 'accounts.Admin', on_delete=models.SET_NULL, null=True, related_name="managed_executives" )

    account_number = models.CharField(max_length=30, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    is_favourite = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    use_personal_rate = models.BooleanField(default=False, help_text="If true, use personal amount_per_min instead of global rates")

    objects = ExecutiveManager()

    USERNAME_FIELD = 'mobile_number'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return f"{self.name} ({self.executive_id})"


class GlobalPricing(models.Model):
    """
    Holds the default global amount_per_min used when no active RateSchedule matches.
    Admin-managed global fallback rate.
    """
    default_amount_per_min = models.DecimalField(
        max_digits=10, decimal_places=2, default=2.0,
        help_text="Default global rate per minute for executives"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Pricing"
        verbose_name_plural = "Global Pricing"

    def __str__(self):
        return f"Global Default: {self.default_amount_per_min}/min"


class RateSchedule(models.Model):
    """
    Time-dependent rate schedules for executives.
    Supports optional time ranges and days of week.
    Higher priority wins in overlaps.
    """
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    name = models.CharField(max_length=100, help_text="Descriptive name for the schedule")
    amount_per_min = models.DecimalField(max_digits=10, decimal_places=2, help_text="Rate per minute during this schedule")
    start_time = models.TimeField(null=True, blank=True, help_text="Start time (optional, if null applies all day)")
    end_time = models.TimeField(null=True, blank=True, help_text="End time (optional, if null applies all day)")
    days_of_week = models.JSONField(default=list, blank=True, help_text="List of day numbers 0-6 (Monday=0), empty means all days")
    active = models.BooleanField(default=True, help_text="Whether this schedule is active")
    priority = models.PositiveIntegerField(default=0, help_text="Higher priority wins in overlaps")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = "Rate Schedule"
        verbose_name_plural = "Rate Schedules"

    def __str__(self):
        time_range = ""
        if self.start_time and self.end_time:
            time_range = f" {self.start_time}-{self.end_time}"
        elif self.start_time:
            time_range = f" from {self.start_time}"
        elif self.end_time:
            time_range = f" until {self.end_time}"
        
        days = ""
        if self.days_of_week:
            day_names = [dict(self.DAYS_OF_WEEK)[d] for d in self.days_of_week if d in dict(self.DAYS_OF_WEEK)]
            days = f" ({', '.join(day_names)})"
        
        return f"{self.name}: {self.amount_per_min}/min{time_range}{days}"

    def matches_time(self, current_time, current_weekday):
        """
        Check if this schedule matches the current time and day.
        """
        # Check if active
        if not self.active:
            return False
        
        # Check days of week (if specified)
        if self.days_of_week and current_weekday not in self.days_of_week:
            return False
        
        # If no time constraints, always matches
        if not self.start_time and not self.end_time:
            return True
        
        # Check time range
        if self.start_time and self.end_time:
            # Handle midnight wrap-around
            if self.start_time <= self.end_time:
                # Same day range
                return self.start_time <= current_time <= self.end_time
            else:
                # Midnight wrap-around (e.g., 23:00 to 05:00)
                return current_time >= self.start_time or current_time <= self.end_time
        elif self.start_time:
            return current_time >= self.start_time
        elif self.end_time:
            return current_time <= self.end_time
        
        return True


from django.db import models
from django.utils import timezone


class ExecutiveStats(models.Model):
    executive = models.OneToOneField(
        "Executive", on_delete=models.CASCADE, related_name="stats"
    )
    coins_per_second = models.FloatField(default=3)  # from user
    amount_per_min = models.DecimalField(max_digits=10, decimal_places=2, default=2.0)
    vault_Balance = models.IntegerField(default=0)

    # Call tracking
    total_on_duty_seconds = models.PositiveIntegerField(default=0)
    total_talk_seconds = models.PositiveIntegerField(default=0)
    total_talk_seconds_today = models.PositiveIntegerField(default=0)
    total_picked_calls = models.PositiveIntegerField(default=0)
    total_missed_calls = models.PositiveIntegerField(default=0)

    total_earnings = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Total lifetime earnings of executive",
    )
    earnings_today = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Earnings for current day (auto-resets daily)",
    )

    pending_payout = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Lifetime payout pending (does not reset daily)",
    )

    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stats for {self.executive.name}"

    # ----------- DAILY RESET LOGIC -----------

    def _reset_if_new_day(self):
        now = timezone.now()
        if self.last_updated.date() != now.date():
            self.earnings_today = 0.00
            self.total_talk_seconds_today = 0
            self.last_updated = now
            self.save(
                update_fields=["earnings_today", "total_talk_seconds_today", "last_updated"]
            )

    @property
    def current_earnings_today(self):
        self._reset_if_new_day()
        return self.earnings_today

    @property
    def current_talk_seconds_today(self):
        self._reset_if_new_day()
        return self.total_talk_seconds_today

    def update_earnings(self, amount, talk_seconds):
        self._reset_if_new_day()
        self.earnings_today += amount
        self.total_talk_seconds_today += talk_seconds
        self.total_earnings += amount
        self.pending_payout += amount
        self.last_updated = timezone.now()
        self.save(
            update_fields=[
                "earnings_today",
                "total_talk_seconds_today",
                "total_earnings",
                "pending_payout",
                "last_updated",
            ]
        )


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


