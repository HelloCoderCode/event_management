from django.contrib import admin

from .models import OrganizerProfile


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "organization_name", "phone")
