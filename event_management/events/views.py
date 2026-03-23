import base64
import csv
import io

import qrcode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMultiAlternatives
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.db.models import Sum, Count
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from django.db import transaction

from .forms import (
    EventForm,
    RegistrationEditForm,
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
    category = request.GET.get("category", "all")
    if category == "all":
        events = Event.objects.all()
    else:
        events = Event.objects.filter(category=category)
    return render(request, "events/home.html", {"events": events, "category": category})


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

                field_values = registration.field_values.select_related("field").all()
                custom_fields = [
                    {
                        "label": value.field.label,
                        "value": value.value or (value.file.name if value.file else ""),
                    }
                    for value in field_values
                ]

                text_message = (
                    "Thanks for registering.\n\n"
                    f"Booking ID: {registration.booking_id}\n"
                    f"Event: {event.title}\n"
                    f"Start: {event.start_date} {event.start_time}\n"
                    f"End: {event.end_date} {event.end_time}\n"
                    f"Location: {event.location}\n"
                    f"Tickets: {ticket_type.name} x {quantity}\n"
                    f"Name: {registration.name}\n"
                    f"Email: {registration.email}\n"
                    f"Phone: {registration.phone}\n"
                )

                html_message = render_to_string(
                    "events/email/registration_email.html",
                    {
                        "event": event,
                        "registration": registration,
                        "ticket_type": ticket_type,
                        "quantity": quantity,
                        "custom_fields": custom_fields,
                    },
                )

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_message,
                    to=[registration.email],
                    cc=[organizer_email] if organizer_email else None,
                )
                email.attach_alternative(html_message, "text/html")
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
    width, height = letter
    margin = 54
    card_x = margin
    card_y = 120
    card_w = width - margin * 2
    card_h = height - 200

    # Card background
    pdf.setFillColorRGB(1, 1, 1)
    pdf.roundRect(card_x, card_y, card_w, card_h, 12, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0.86, 0.86, 0.86)
    pdf.roundRect(card_x, card_y, card_w, card_h, 12, stroke=1, fill=0)

    # Accent bar
    pdf.setFillColorRGB(0.0, 0.44, 0.89)
    pdf.rect(card_x, card_y + card_h - 6, card_w, 6, stroke=0, fill=1)

    # Dark header band
    header_h = 120
    pdf.setFillColorRGB(0.1, 0.1, 0.12)
    pdf.rect(card_x, card_y + card_h - 6 - header_h, card_w, header_h, stroke=0, fill=1)

    # Header text
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(card_x + 20, card_y + card_h - 6 - 24, "EVENT TICKET")
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(card_x + 20, card_y + card_h - 6 - 48, registration.event.title)
    pdf.setFont("Helvetica", 10)
    pdf.setFillColorRGB(0.8, 0.8, 0.8)
    pdf.drawString(
        card_x + 20,
        card_y + card_h - 6 - 70,
        f"{registration.event.start_date} {registration.event.start_time} · {registration.event.location}",
    )

    # Ticket badge
    pdf.setFillColorRGB(0.25, 0.25, 0.28)
    badge_w = 150
    badge_h = 22
    badge_x = card_x + card_w - badge_w - 20
    badge_y = card_y + card_h - 6 - 60
    pdf.roundRect(badge_x, badge_y, badge_w, badge_h, 10, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica", 9)
    pdf.drawCentredString(
        badge_x + badge_w / 2,
        badge_y + 7,
        f"{registration.ticket_type.name} x {registration.quantity}",
    )

    # Body section
    body_top = card_y + card_h - 6 - header_h - 20
    left_x = card_x + 20
    right_x = card_x + card_w - 160

    pdf.setFillColorRGB(0.1, 0.1, 0.12)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left_x, body_top, "BOOKING ID")
    pdf.setFillColorRGB(0.0, 0.44, 0.89)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left_x, body_top - 16, registration.booking_id)

    pdf.setFillColorRGB(0.1, 0.1, 0.12)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left_x, body_top - 40, f"Name: {registration.name}")
    pdf.drawString(left_x, body_top - 56, f"Email: {registration.email}")
    pdf.drawString(left_x, body_top - 72, f"Phone: {registration.phone}")

    # QR code
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setStrokeColorRGB(0.85, 0.85, 0.85)
    pdf.roundRect(right_x - 10, body_top - 120, 140, 140, 10, stroke=1, fill=1)
    pdf.drawImage(ImageReader(img_buffer), right_x, body_top - 110, width=120, height=120)

    # Footer note
    pdf.setFillColorRGB(0.4, 0.4, 0.45)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        card_x + 20,
        card_y + 20,
        "Show this ticket or QR code at entry. Keep this PDF for offline access.",
    )

    pdf.showPage()
    pdf.save()
    return response


@login_required
def organizer_dashboard(request):
    events = (
        Event.objects.filter(organizer=request.user)
        .annotate(
            reg_count=Count("registrations"),
            sold_total=Sum("ticket_types__sold_quantity"),
            capacity_total=Sum("ticket_types__total_quantity"),
        )
    )
    for event in events:
        if not event.public_id:
            event.save()
        capacity = event.capacity_total or 0
        reg_count = event.reg_count or 0
        if capacity > 0:
            event.reg_percent = int(min(100, (reg_count / capacity) * 100))
        else:
            event.reg_percent = 0
    total_registrations = Registration.objects.filter(event__organizer=request.user).count()
    total_checked_in = Registration.objects.filter(
        event__organizer=request.user, checked_in=True
    ).count()
    tickets_sold = (
        TicketType.objects.filter(event__organizer=request.user).aggregate(
            total=Sum("sold_quantity")
        )["total"]
        or 0
    )
    return render(
        request,
        "events/organizer/dashboard.html",
        {
            "events": events,
            "total_registrations": total_registrations,
            "total_checked_in": total_checked_in,
            "tickets_sold": tickets_sold,
        },
    )


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
def delete_event_confirm(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    if request.method == "POST":
    with transaction.atomic():
        # Remove registrations first so protected ticket types can be deleted.
        event.registrations.all().delete()
        event.delete()
    messages.success(request, "Event and all associated data deleted.")
    return redirect("events:organizer_dashboard")



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
    registrations = event.registrations.select_related("ticket_type").prefetch_related(
        "field_values__field"
    )
    custom_fields = list(
        event.registration_fields.exclude(key__in=["name", "email", "phone"]).all()
    )
    rows = []
    for reg in registrations:
        values_by_field_id = {}
        for value in reg.field_values.all():
            if value.field.key in {"name", "email", "phone"}:
                continue
            display_value = value.value
            if value.file:
                display_value = value.file.name
            values_by_field_id[value.field_id] = display_value
        rows.append(
            {
                "registration": reg,
                "qr_data": _qr_base64(reg.booking_id),
                "values_by_field_id": values_by_field_id,
            }
        )
    return render(
        request,
        "events/organizer/registrations.html",
        {
            "event": event,
            "rows": rows,
            "custom_fields": custom_fields,
            "colspan": 8 + len(custom_fields),
        },
    )


@login_required
def registration_edit(request, event_id, registration_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    registration = get_object_or_404(Registration, id=registration_id, event=event)
    ensure_default_fields(event)
    if request.method == "POST":
        form = RegistrationEditForm(
            request.POST, request.FILES, event=event, registration=registration
        )
        if form.is_valid():
            new_ticket = form.cleaned_data["ticket_type"]
            new_qty = form.cleaned_data["quantity"]

            if new_ticket == registration.ticket_type:
                extra_needed = new_qty - registration.quantity
                if extra_needed > new_ticket.available_quantity:
                    form.add_error(None, "Not enough tickets available for this change.")
                    return render(
                        request,
                        "events/organizer/registration_edit.html",
                        {"form": form, "event": event, "registration": registration},
                    )
                new_ticket.sold_quantity += extra_needed
                new_ticket.save()
            else:
                if new_qty > new_ticket.available_quantity:
                    form.add_error(None, "Not enough tickets available for this change.")
                    return render(
                        request,
                        "events/organizer/registration_edit.html",
                        {"form": form, "event": event, "registration": registration},
                    )
                registration.ticket_type.sold_quantity = max(
                    registration.ticket_type.sold_quantity - registration.quantity, 0
                )
                registration.ticket_type.save()
                new_ticket.sold_quantity += new_qty
                new_ticket.save()

            registration.name = form.cleaned_data["name"]
            registration.email = form.cleaned_data["email"]
            registration.phone = form.cleaned_data["phone"]
            registration.ticket_type = new_ticket
            registration.quantity = new_qty
            registration.save()

            for field in event.registration_fields.exclude(key__in=["name", "email", "phone"]):
                value = form.cleaned_data.get(field.key, "")
                field_value, _ = RegistrationFieldValue.objects.get_or_create(
                    registration=registration, field=field
                )
                if field.field_type == RegistrationField.FIELD_FILE:
                    if value:
                        field_value.file = value
                else:
                    field_value.value = str(value)
                field_value.save()

            messages.success(request, "Registration updated.")
            return redirect("events:registrations_list", event_id=event.public_id)
    else:
        form = RegistrationEditForm(event=event, registration=registration)

    return render(
        request,
        "events/organizer/registration_edit.html",
        {"form": form, "event": event, "registration": registration},
    )


@login_required
def registration_delete(request, event_id, registration_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    registration = get_object_or_404(Registration, id=registration_id, event=event)
    if request.method == "POST":
        ticket = registration.ticket_type
        ticket.sold_quantity = max(ticket.sold_quantity - registration.quantity, 0)
        ticket.save()
        registration.delete()
        messages.success(request, "Registration deleted.")
    return redirect("events:registrations_list", event_id=event.public_id)


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


@login_required
def checkin_dashboard(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    status = request.GET.get("status", "all")
    registrations = event.registrations.select_related("ticket_type")
    if status == "checked_in":
        registrations = registrations.filter(checked_in=True)
    elif status == "not_checked_in":
        registrations = registrations.filter(checked_in=False)
    return render(
        request,
        "events/organizer/checkin_dashboard.html",
        {"event": event, "registrations": registrations, "status": status},
    )


@login_required
def checkin_scan(request, event_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    booking_id = request.GET.get("booking_id", "")
    registration = None
    error = ""
    if booking_id:
        registration = event.registrations.filter(booking_id=booking_id).first()
        if not registration:
            error = "No registration found for this QR code."
    return render(
        request,
        "events/organizer/checkin_scan.html",
        {"event": event, "registration": registration, "error": error},
    )


@login_required
def checkin_confirm(request, event_id, registration_id):
    event = get_object_or_404(Event, public_id=event_id, organizer=request.user)
    registration = get_object_or_404(Registration, id=registration_id, event=event)
    if request.method == "POST":
        registration.checked_in = True
        registration.checked_in_at = timezone.now()
        registration.save(update_fields=["checked_in", "checked_in_at"])
        messages.success(request, "Checked in successfully.")
    return redirect("events:checkin_scan", event_id=event.public_id)
