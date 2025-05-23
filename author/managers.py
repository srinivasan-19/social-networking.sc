from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where displayName is the unique identifiers
    for authentication instead of usernames.
    """
    def create_user(self, displayName, password, **extra_fields):
        """
        Create and save a user with the given displayName and password.
        """
        if not displayName:
            raise ValueError(_("The displayName must be set"))
        
        user = self.model(displayName=displayName, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, displayName, password, **extra_fields):
        """
        Create and save a SuperUser with the given displayName and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))
        return self.create_user(displayName, password, **extra_fields)