from django.contrib.auth.models import BaseUserManager

class AdminManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field is required")
        if not name:
            raise ValueError("The Name field is required")

        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, name, password, **extra_fields)


class ExecutiveManager(BaseUserManager):
    def create_user(self, mobile_number, name, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError("The Mobile Number field is required")
        if not name:
            raise ValueError("The Name field is required")

        user = self.model(mobile_number=mobile_number, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, name, password=None, **extra_fields):
        raise ValueError("Executives cannot be superusers")

class UserManager(BaseUserManager):
    def create_user(self, mobile_number, name, password=None, **extra_fields):
        if not mobile_number:
            raise ValueError("The Mobile Number field is required")
        if not name:
            raise ValueError("The Name field is required")

        user = self.model(mobile_number=mobile_number, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, mobile_number, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get('is_superuser') is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(mobile_number, name, password, **extra_fields)
