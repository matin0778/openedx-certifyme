from django.urls import path

from .views import health

app_name = "certifyme"

urlpatterns = [
    path("health", health, name="health"),
    path("health/", health, name="health-slash"),
]
