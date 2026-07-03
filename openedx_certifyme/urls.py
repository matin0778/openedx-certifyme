from django.urls import path

from openedx_certifyme.views.health import health
from openedx_certifyme.views.instructor import (
    bulk_issue_certificates,
    course_certificates,
    issue_certificate_for_user,
    resend_certificate_email,
    retry_certificate,
    retry_failed_certificates,
    revoke_certificate,
)
from openedx_certifyme.views.student import my_certificates, verify_certificate

app_name = "certifyme"

urlpatterns = [
    path("health", health, name="health"),
    path("health/", health, name="health-slash"),
    path("certificates/", my_certificates, name="my-certificates"),
    path("certificates/<int:pk>/verify/", verify_certificate, name="verify-certificate"),
    path("instructor/<str:course_id>/", course_certificates, name="instructor-course-certificates"),
    path("instructor/<str:course_id>/issue/", issue_certificate_for_user, name="instructor-issue"),
    path("instructor/<str:course_id>/bulk-issue/", bulk_issue_certificates, name="instructor-bulk-issue"),
    path("instructor/<str:course_id>/retry-failed/", retry_failed_certificates, name="instructor-retry-failed"),
    path(
        "instructor/<str:course_id>/certificates/<int:pk>/retry/",
        retry_certificate,
        name="instructor-retry",
    ),
    path(
        "instructor/<str:course_id>/certificates/<int:pk>/revoke/",
        revoke_certificate,
        name="instructor-revoke",
    ),
    path(
        "instructor/<str:course_id>/certificates/<int:pk>/resend/",
        resend_certificate_email,
        name="instructor-resend",
    ),
]
