from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import OrganizerProfile


class OrganizerRegisterForm(UserCreationForm):
    email = forms.EmailField()
    organization_name = forms.CharField(max_length=150, required=False)
    phone = forms.CharField(max_length=30, required=False)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            OrganizerProfile.objects.update_or_create(
                user=user,
                defaults={
                    "organization_name": self.cleaned_data.get("organization_name", ""),
                    "phone": self.cleaned_data.get("phone", ""),
                },
            )
        return user
