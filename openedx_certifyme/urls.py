from django.urls import path

from openedx_certifyme.views.health import health
from openedx_certifyme.views.student import my_certificates, verify_certificate

app_name = "certifyme"

urlpatterns = [
    path("health", health, name="health"),
    path("health/", health, name="health-slash"),
    path("certificates/", my_certificates, name="my-certificates"),
    path("certificates/<int:pk>/verify/", verify_certificate, name="verify-certificate"),
]
