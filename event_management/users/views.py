from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import OrganizerRegisterForm


class OrganizerLoginView(LoginView):
    template_name = "users/login.html"


class OrganizerLogoutView(LogoutView):
    pass


def register(request):
    if request.user.is_authenticated:
        return redirect("events:organizer_dashboard")
    if request.method == "POST":
        form = OrganizerRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("events:organizer_dashboard")
    else:
        form = OrganizerRegisterForm()
    return render(request, "users/register.html", {"form": form})
