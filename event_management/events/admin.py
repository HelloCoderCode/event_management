from django.contrib import admin

from .models import Event, Registration, RegistrationField, RegistrationFieldValue, TicketType


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0


class RegistrationFieldInline(admin.TabularInline):
    model = RegistrationField
    extra = 0


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "start_time", "location", "organizer")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [TicketTypeInline, RegistrationFieldInline]


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "price", "total_quantity", "sold_quantity")
    list_filter = ("event",)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("booking_id", "name", "email", "event", "ticket_type", "quantity")
    list_filter = ("event", "ticket_type")


@admin.register(RegistrationField)
class RegistrationFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "event", "field_type", "required")
    list_filter = ("event",)


@admin.register(RegistrationFieldValue)
class RegistrationFieldValueAdmin(admin.ModelAdmin):
    list_display = ("registration", "field")
