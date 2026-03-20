from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("", views.home, name="home"),
    path("events/<slug:slug>/", views.event_detail, name="event_detail"),
    path("events/<slug:slug>/register/", views.registration_form, name="registration_form"),
    path("ticket/<str:booking_id>/", views.ticket_detail, name="ticket_detail"),
    path("ticket/<str:booking_id>/pdf/", views.ticket_pdf, name="ticket_pdf"),
    path("organizer/dashboard/", views.organizer_dashboard, name="organizer_dashboard"),
    path("organizer/events/create/", views.event_create, name="event_create"),
    path("organizer/events/<str:event_id>/manage/", views.event_manage, name="event_manage"),
    path(
        "organizer/events/<str:event_id>/toggle/",
        views.toggle_event_status,
        name="toggle_event_status",
    ),
    path("organizer/events/<str:event_id>/edit/", views.event_edit, name="event_edit"),
    path(
        "organizer/events/<str:event_id>/tickets/add/",
        views.add_ticket_type,
        name="add_ticket_type",
    ),
    path(
        "organizer/events/<str:event_id>/tickets/<int:ticket_id>/edit/",
        views.edit_ticket_type,
        name="edit_ticket_type",
    ),
    path(
        "organizer/events/<str:event_id>/fields/manage/",
        views.manage_registration_fields,
        name="manage_registration_fields",
    ),
    path(
        "organizer/events/<str:event_id>/registrations/",
        views.registrations_list,
        name="registrations_list",
    ),
    path(
        "organizer/events/<str:event_id>/registrations/export/",
        views.registrations_export_csv,
        name="registrations_export_csv",
    ),
]
