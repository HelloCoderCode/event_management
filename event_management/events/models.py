from django.conf import settings
from django.db import models
from django.utils.crypto import get_random_string
from django.utils.text import slugify


class Event(models.Model):
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="events"
    )
    public_id = models.CharField(max_length=12, unique=True, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    keywords = models.CharField(max_length=255, blank=True)
    registrations_closed = models.BooleanField(default=False)
    registration_deadline = models.DateTimeField(blank=True, null=True)
    location = models.CharField(max_length=255)
    image = models.ImageField(upload_to="events/images/", blank=True, null=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "start_time"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.public_id:
            public_id = get_random_string(10).upper()
            while Event.objects.filter(public_id=public_id).exclude(pk=self.pk).exists():
                public_id = get_random_string(10).upper()
            self.public_id = public_id
        if not self.slug:
            base_slug = slugify(self.title) or get_random_string(6).lower()
            slug = base_slug
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{get_random_string(4).lower()}"
            self.slug = slug
        super().save(*args, **kwargs)


class TicketType(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="ticket_types")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    total_quantity = models.PositiveIntegerField()
    sold_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("event", "name")

    def __str__(self) -> str:
        return f"{self.event.title} - {self.name}"

    @property
    def available_quantity(self) -> int:
        return max(self.total_quantity - self.sold_quantity, 0)


class Registration(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registrations")
    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.PROTECT, related_name="registrations"
    )
    quantity = models.PositiveIntegerField()
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    booking_id = models.CharField(max_length=20, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.booking_id} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.booking_id:
            booking_id = f"EVT-{get_random_string(8).upper()}"
            while Registration.objects.filter(booking_id=booking_id).exists():
                booking_id = f"EVT-{get_random_string(8).upper()}"
            self.booking_id = booking_id
        super().save(*args, **kwargs)


class RegistrationField(models.Model):
    FIELD_TEXT = "text"
    FIELD_NUMBER = "number"
    FIELD_EMAIL = "email"
    FIELD_DATE = "date"
    FIELD_FILE = "file"

    FIELD_CHOICES = [
        (FIELD_TEXT, "Text"),
        (FIELD_NUMBER, "Number"),
        (FIELD_EMAIL, "Email"),
        (FIELD_DATE, "Date"),
        (FIELD_FILE, "File"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="registration_fields")
    label = models.CharField(max_length=120)
    key = models.SlugField(max_length=140, blank=True)
    field_type = models.CharField(max_length=20, choices=FIELD_CHOICES, default=FIELD_TEXT)
    required = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    class Meta:
        unique_together = ("event", "key")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.event.title} - {self.label}"

    def save(self, *args, **kwargs):
        if not self.key:
            base_key = slugify(self.label) or get_random_string(6).lower()
            key = base_key
            while RegistrationField.objects.filter(event=self.event, key=key).exclude(
                pk=self.pk
            ).exists():
                key = f"{base_key}-{get_random_string(4).lower()}"
            self.key = key
        super().save(*args, **kwargs)


class RegistrationFieldValue(models.Model):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="field_values"
    )
    field = models.ForeignKey(RegistrationField, on_delete=models.CASCADE)
    value = models.TextField(blank=True)
    file = models.FileField(upload_to="registrations/files/", blank=True, null=True)

    def __str__(self) -> str:
        return f"{self.registration.booking_id} - {self.field.label}"
