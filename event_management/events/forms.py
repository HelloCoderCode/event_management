from django import forms
from django.forms import modelformset_factory

from .models import Event, RegistrationField, TicketType


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "location",
            "category",
            "keywords",
            "registration_deadline",
            "image",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "registration_deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = ["name", "price", "total_quantity"]


class RegistrationFieldForm(forms.ModelForm):
    class Meta:
        model = RegistrationField
        fields = ["label", "field_type", "required"]


RegistrationFieldFormSet = modelformset_factory(
    RegistrationField,
    form=RegistrationFieldForm,
    extra=1,
    can_delete=True,
)


class RegistrationForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)
    ticket_type = forms.ModelChoiceField(queryset=TicketType.objects.none(), widget=forms.HiddenInput)
    quantity = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, event=None, **kwargs):
        super().__init__(*args, **kwargs)
        if event is None:
            return
        self.fields["ticket_type"].queryset = event.ticket_types.all()
        for field in event.registration_fields.all():
            if field.field_type == RegistrationField.FIELD_NUMBER:
                form_field = forms.IntegerField(required=field.required, label=field.label)
            elif field.field_type == RegistrationField.FIELD_EMAIL:
                form_field = forms.EmailField(required=field.required, label=field.label)
            elif field.field_type == RegistrationField.FIELD_DATE:
                form_field = forms.DateField(
                    required=field.required,
                    label=field.label,
                    widget=forms.DateInput(attrs={"type": "date"}),
                )
            elif field.field_type == RegistrationField.FIELD_FILE:
                form_field = forms.FileField(required=field.required, label=field.label)
            else:
                form_field = forms.CharField(required=field.required, label=field.label)
            self.fields[field.key] = form_field


class RegistrationEditForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30)
    ticket_type = forms.ModelChoiceField(queryset=TicketType.objects.none())
    quantity = forms.IntegerField(min_value=1)

    def __init__(self, *args, event=None, registration=None, **kwargs):
        super().__init__(*args, **kwargs)
        if event is None:
            return
        self.fields["ticket_type"].queryset = event.ticket_types.all()
        if registration:
            self.initial.update(
                {
                    "name": registration.name,
                    "email": registration.email,
                    "phone": registration.phone,
                    "ticket_type": registration.ticket_type,
                    "quantity": registration.quantity,
                }
            )
        for field in event.registration_fields.exclude(key__in=["name", "email", "phone"]):
            if field.field_type == RegistrationField.FIELD_NUMBER:
                form_field = forms.IntegerField(required=field.required, label=field.label)
            elif field.field_type == RegistrationField.FIELD_EMAIL:
                form_field = forms.EmailField(required=field.required, label=field.label)
            elif field.field_type == RegistrationField.FIELD_DATE:
                form_field = forms.DateField(
                    required=field.required,
                    label=field.label,
                    widget=forms.DateInput(attrs={"type": "date"}),
                )
            elif field.field_type == RegistrationField.FIELD_FILE:
                form_field = forms.FileField(required=False, label=field.label)
            else:
                form_field = forms.CharField(required=field.required, label=field.label)
            self.fields[field.key] = form_field

            if registration:
                existing = registration.field_values.filter(field=field).first()
                if existing and not field.field_type == RegistrationField.FIELD_FILE:
                    self.initial[field.key] = existing.value
