from django.conf import settings
from django.db import models


class OrganizerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="organizer_profile"
    )
    organization_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self) -> str:
        return self.user.username
