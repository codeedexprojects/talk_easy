from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, Group, Permission
from django.db import models
from django.utils.timezone import now
from .managers import AdminManager  # You'll need a custom manager

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
