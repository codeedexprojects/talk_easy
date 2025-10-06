from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, Group, Permission
from django.db import models
from django.utils.timezone import now
from .managers import AdminManager  
from django.utils import timezone

class Admin(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=15, unique=True, null=True)

    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)
    otp_verified_at = models.DateTimeField(blank=True, null=True)

    is_staff = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    is_banned = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=now)

    ROLE_CHOICES = [
        ('hr_user', 'HR - User'),
        ('hr_executive', 'HR - Executive'),
        ('manager_user', 'Manager - User'),
        ('manager_executive', 'Manager - Executive'),
        ('superuser', 'Superuser'),
        ('other', 'Other')
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='other')

    groups = models.ManyToManyField(Group, related_name='admin_groups', blank=True)
    user_permissions = models.ManyToManyField(Permission, related_name='admin_permissions', blank=True)

    objects = AdminManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    def __str__(self):
        return f"{self.name} ({self.email})"



class AdminSession(models.Model):
    admin = models.ForeignKey('Admin', on_delete=models.CASCADE, related_name='login_sessions')
    device_name = models.CharField(max_length=255, blank=True)
    device_type = models.CharField(max_length=50, blank=True) 
    browser = models.CharField(max_length=100, blank=True)
    os = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    jwt_jti = models.CharField(max_length=255, unique=True, db_index=True) 
    is_active = models.BooleanField(default=True, db_index=True)
    last_activity = models.DateTimeField(auto_now=True)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['admin', 'is_active']),
            models.Index(fields=['jwt_jti']),
        ]
        verbose_name = 'Admin Session'
        verbose_name_plural = 'Admin Sessions'
    
    def __str__(self):
        return f"{self.admin.email} - {self.device_type or 'Unknown'} - {self.ip_address}"
    
    def deactivate(self):
        """Deactivate this session"""
        self.is_active = False
        self.logout_time = timezone.now()
        self.save(update_fields=['is_active', 'logout_time'])