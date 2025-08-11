from django.contrib.auth.models import BaseUserManager

class CustomUserManager(BaseUserManager):
    def create_user(self, mobile_number, name, email=None, password=None, role='user', **extra_fields):
        if not mobile_number:
            raise ValueError("The Mobile Number field is required")
        if not name:
            raise ValueError("The Name field is required")
        
        email = self.normalize_email(email) if email else None
        user = self.model(
            mobile_number=mobile_number,
            name=name,
            email=email,
            role=role,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, name, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(mobile_number, name, email, password, **extra_fields)
