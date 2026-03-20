import base64
import csv
import io

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .forms import (
    EventForm,
    RegistrationFieldFormSet,
    RegistrationForm,
    TicketTypeForm,
)
from .models import (
    Event,
    Registration,
    RegistrationField,
    RegistrationFieldValue,
    TicketType,
)


def ensure_default_fields(event):
    defaults = [
        {"key": "name", "label": "Name", "field_type": RegistrationField.FIELD_TEXT},
        {"key": "email", "label": "Email", "field_type": RegistrationField.FIELD_EMAIL},
        {"key": "phone", "label": "Phone", "field_type": RegistrationField.FIELD_TEXT},
    ]
    for item in defaults:
        field, created = RegistrationField.objects.get_or_create(
            event=event,
            key=item["key"],
            defaults={
                "label": item["label"],
                "field_type": item["field_type"],
                "required": True,
                "is_system": True,
            },
        )
        if not created and not field.is_system:
            field.is_system = True
            field.save(update_fields=["is_system"])


def home(request):
    events = Event.objects.all()
    return render(request, "events/home.html", {"events": events})


def event_detail(request, slug):
    event = get_object_or_404(Event, slug=slug)
    ticket_types = event.ticket_types.filter(is_active=True)
    has_available = any(ticket.available_quantity > 0 for ticket in ticket_types)
    registration_closed = event.registrations_closed
    if event.registration_deadline and event.registration_deadline <= timezone.now():
        registration_closed = True
    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "ticket_types": ticket_types,
            "has_available": has_available,
            "registration_closed": registration_closed,
        },
    )


def _get_selected_ticket(event, ticket_type_id):
    if ticket_type_id:
        return event.ticket_types.filter(id=ticket_type_id, is_active=True).first()
    return event.ticket_types.filter(is_active=True).first()


def registration_form(request, slug):
    event = get_object_or_404(Event, slug=slug)
    ensure_default_fields(event)
    if event.registrations_closed:
        messages.error(request, "Registrations are closed for this event.")
        return redirect("events:event_detail", slug=event.slug)
    if event.registration_deadline and event.registration_deadline <= timezone.now():
        messages.error(request, "Registration deadline has passed.")
        return redirect("events:event_detail", slug=event.slug)
    if not event.ticket_types.filter(is_active=True).exists():
        messages.info(request, "Ticket types are not available yet.")
        return redirect("events:event_detail", slug=event.slug)
    ticket_type_id = request.GET.get("ticket_type") if request.method == "GET" else None
    quantity = request.GET.get("quantity") if request.method == "GET" else None

    selected_ticket = _get_selected_ticket(event, ticket_type_id)
    selected_quantity = 1
    if quantity and str(quantity).isdigit():
        selected_quantity = max(int(quantity), 1)
    if selected_ticket and selected_ticket.available_quantity == 0:
        messages.error(request, "Selected ticket type is sold out.")
        return redirect("events:event_detail", slug=event.slug)

    if request.method == "POST":
        form = RegistrationForm(request.POST, request.FILES, event=event)
        selected_ticket = _get_selected_ticket(event, request.POST.get("ticket_type"))
        posted_qty = request.POST.get("quantity")
        if posted_qty and str(posted_qty).isdigit():
            selected_quantity = max(int(posted_qty), 1)
        else:
            selected_quantity = 1
        if form.is_valid():
            ticket_type = form.cleaned_data["ticket_type"]
            quantity = form.cleaned_data["quantity"]
            if quantity > ticket_type.available_quantity:
                form.add_error(None, "Not enough tickets available for this selection.")
            else:
                registration = Registration.objects.create(
                    event=event,
                    ticket_type=ticket_type,
                    quantity=quantity,
                    name=form.cleaned_data["name"],
                    email=form.cleaned_data["email"],
                    phone=form.cleaned_data["phone"],
                )
                for field in event.registration_fields.all():
                    value = form.cleaned_data.get(field.key, "")
                    if field.field_type == RegistrationField.FIELD_FILE:
                        RegistrationFieldValue.objects.create(
                            registration=registration, field=field, file=value
                        )
                    else:
                        RegistrationFieldValue.objects.create(
                            registration=registration, field=field, value=str(value)
                        )

                ticket_type.sold_quantity += quantity
                ticket_type.save()

                qr_png = io.BytesIO()
                qr_email = qrcode.QRCode(box_size=6, border=2)
                qr_email.add_data(registration.booking_id)
                qr_email.make(fit=True)
                qr_img = qr_email.make_image(fill_color="black", back_color="white")
                qr_img.save(qr_png, format="PNG")

                organizer_email = event.organizer.email if event.organizer else ""
                subject = f"Your ticket for {event.title}"
                message = (
                    "Thanks for registering.\n\n"
                    f"Booking ID: {registration.booking_id}\n"
                    f"Event: {event.title}\n"
                    f"Dates: {event.start_date} to {event.end_date}\n"
                    f"Times: {event.start_time} to {event.end_time}\n"
                    f"Location: {event.location}\n"
                    f"Tickets: {ticket_type.name} x {quantity}\n"
                    f"Name: {registration.name}\n"
                    f"Email: {registration.email}\n"
                    f"Phone: {registration.phone}\n"
                )

                email = EmailMessage(
                    subject=subject,
                    body=message,
                    to=[registration.email],
                    cc=[organizer_email] if organizer_email else None,
                )
                email.attach(
                    filename=f"ticket-{registration.booking_id}.png",
                    content=qr_png.getvalue(),
                    mimetype="image/png",
                )
                email.send(fail_silently=True)

                return redirect("events:ticket_detail", booking_id=registration.booking_id)
    else:
        initial = {}
        if selected_ticket:
            initial["ticket_type"] = selected_ticket
        initial["quantity"] = selected_quantity
        form = RegistrationForm(event=event, initial=initial)

    display_fields = []
    for field in event.registration_fields.all():
        if field.key == "name":
            form.fields["name"].label = field.label
            form.fields["name"].required = field.required
            display_fields.append(form["name"])
        elif field.key == "email":
            form.fields["email"].label = field.label
            form.fields["email"].required = field.required
            display_fields.append(form["email"])
        elif field.key == "phone":
            form.fields["phone"].label = field.label
            form.fields["phone"].required = field.required
            display_fields.append(form["phone"])
        else:
            display_fields.append(form[field.key])

    return render(
        request,
        "events/registration_form.html",
        {
            "event": event,
            "form": form,
            "display_fields": display_fields,
            "selected_ticket": selected_ticket,
            "selected_quantity": selected_quantity,
        },
    )


def _qr_base64(data):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def ticket_detail(request, booking_id):
    registration = get_object_or_404(Registration, booking_id=booking_id)
    qr_data = _qr_base64(registration.booking_id)
    return render(
        request,
        "events/ticket_detail.html",
        {"registration": registration, "qr_data": qr_data},
    )


def ticket_pdf(request, booking_id):
    registration = get_object_or_404(Registration, booking_id=booking_id)

    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(registration.booking_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = io.BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="ticket-{booking_id}.pdf"'

    pdf = canvas.Canvas(response, pagesize=letter)
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, 750, "Event Ticket")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(72, 720, f"Booking ID: {registration.booking_id}")
    pdf.drawString(72, 700, f"Name: {registration.name}")
    pdf.drawString(72, 680, f"Email: {registration.email}")
    pdf.drawString(72, 660, f"Event: {registration.event.title}")
    pdf.drawString(72, 640, f"Ticket Type: {registration.ticket_type.name}")
    pdf.drawString(72, 620, f"Quantity: {registration.quantity}")

    pdf.drawImage(ImageReader(img_buffer), 72, 500, width=120, height=120)
    pdf.showPage()
    pdf.save()
    return response


@login_required
def organizer_dashboard(request):
    events = Event.objects.filter(organizer=request.user)
    for event in events:
        if not event.public_id:
            event.save()
    return render(request, "events/organizer/dashboard.html", {"events": events})


@login_required
def event_create(request):
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.organizer = request.user
            event.save()
            ensure_default_fields(event)
            messages.success(request, "Event created. Add ticket types next.")
            return redirect("events:event_manage", event_id=event.public_id)
    else:
        form = EventForm()
    return render(request, "events/organizer/event_form.html", {"form": form, "mode": "create"})


@login_required
def event_manage(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    ensure_default_fields(event)
    return render(
        request,
        "events/organizer/event_manage.html",
        {
            "event": event,
            "ticket_types": event.ticket_types.all(),
            "fields": event.registration_fields.all(),
        },
    )


@login_required
def toggle_event_status(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    event.registrations_closed = not event.registrations_closed
    event.save(update_fields=["registrations_closed"])
    if event.registrations_closed:
        messages.success(request, "Event registrations are now closed.")
    else:
        messages.success(request, "Event registrations are now open.")
    return redirect("events:event_manage", event_id=event.public_id)


@login_required
def event_edit(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated.")
            return redirect("events:event_manage", event_id=event.public_id)
    else:
        form = EventForm(instance=event)
    return render(
        request,
        "events/organizer/event_form.html",
        {"form": form, "event": event, "mode": "edit"},
    )


@login_required
def add_ticket_type(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    if request.method == "POST":
        form = TicketTypeForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.event = event
            ticket.save()
            messages.success(request, "Ticket type added.")
            return redirect("events:event_manage", event_id=event.public_id)
    else:
        form = TicketTypeForm()
    return render(
        request,
        "events/organizer/ticket_form.html",
        {"form": form, "event": event},
    )


@login_required
def edit_ticket_type(request, event_id, ticket_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    ticket = get_object_or_404(TicketType, id=ticket_id, event=event)
    if request.method == "POST":
        form = TicketTypeForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            messages.success(request, "Ticket type updated.")
            return redirect("events:event_manage", event_id=event.public_id)
    else:
        form = TicketTypeForm(instance=ticket)
    return render(
        request,
        "events/organizer/ticket_form.html",
        {"form": form, "event": event, "ticket": ticket},
    )


@login_required
def delete_ticket_type(request, event_id, ticket_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    ticket = get_object_or_404(TicketType, id=ticket_id, event=event)
    if request.method == "POST":
        ticket.delete()
        messages.success(request, "Ticket type deleted.")
    return redirect("events:event_manage", event_id=event.public_id)


@login_required
def toggle_ticket_type(request, event_id, ticket_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    ticket = get_object_or_404(TicketType, id=ticket_id, event=event)
    ticket.is_active = not ticket.is_active
    ticket.save(update_fields=["is_active"])
    if ticket.is_active:
        messages.success(request, "Ticket type activated.")
    else:
        messages.success(request, "Ticket type deactivated.")
    return redirect("events:event_manage", event_id=event.public_id)


@login_required
def manage_registration_fields(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    ensure_default_fields(event)
    queryset = event.registration_fields.all()
    if request.method == "POST":
        formset = RegistrationFieldFormSet(request.POST, queryset=queryset)
        for form in formset.forms:
            if form.instance.is_system and "DELETE" in form.fields:
                form.fields["DELETE"].disabled = True
        if formset.is_valid():
            instances = formset.save(commit=False)
            for instance in instances:
                instance.event = event
                instance.save()
            for obj in formset.deleted_objects:
                if not obj.is_system:
                    obj.delete()
            messages.success(request, "Registration fields updated.")
            return redirect("events:event_manage", event_id=event.public_id)
    else:
        formset = RegistrationFieldFormSet(queryset=queryset)
        for form in formset.forms:
            if form.instance.is_system and "DELETE" in form.fields:
                form.fields["DELETE"].disabled = True
    return render(
        request,
        "events/organizer/fields_manage.html",
        {"formset": formset, "event": event},
    )


@login_required
def registrations_list(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    registrations = event.registrations.select_related("ticket_type")
    return render(
        request,
        "events/organizer/registrations.html",
        {"event": event, "registrations": registrations},
    )


@login_required
def registrations_export_csv(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    registrations = event.registrations.select_related("ticket_type")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="registrations-{event.public_id}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(["Name", "Email", "Phone", "Ticket Type", "Quantity", "Booking ID"])
    for reg in registrations:
        writer.writerow(
            [reg.name, reg.email, reg.phone, reg.ticket_type.name, reg.quantity, reg.booking_id]
        )
    return response
