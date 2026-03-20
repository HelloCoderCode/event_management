from django.urls import path

from .views import OrganizerLoginView, OrganizerLogoutView, register

app_name = "users"

urlpatterns = [
    path("login/", OrganizerLoginView.as_view(), name="login"),
    path("logout/", OrganizerLogoutView.as_view(), name="logout"),
    path("register/", register, name="register"),
]
