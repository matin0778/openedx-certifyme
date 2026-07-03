"""
Database models for the CertifyMe plugin.

``CertifyMeConfiguration`` is a `ConfigurationModel`_, the standard Open
edX extension point for admin-editable, versioned configuration
(``enabled`` toggle, automatic change history, cached ``.current()``
lookup) — used throughout edx-platform (e.g. certificate generation,
programs, credentials configs). We reuse it instead of hand-rolling a
settings table + caching layer.

.. _ConfigurationModel: https://github.com/openedx/django-config-models
"""

from config_models.models import ConfigurationModel
from django.conf import settings
from django.db import models
from opaque_keys.edx.django.models import CourseKeyField


class CertifyMeConfiguration(ConfigurationModel):
    """
    Admin-editable configuration for the CertifyMe integration.

    Every save creates a new row (``ConfigurationModel`` semantics), so
    changes are fully auditable via the Django admin history view.
    ``CertifyMeConfiguration.current()`` returns the latest entry.
    """

    api_url = models.URLField(
        max_length=255,
        blank=True,
        help_text="Base URL of the CertifyMe API, e.g. https://api.certifyme.online",
    )
    api_key = models.CharField(
        max_length=255,
        blank=True,
        help_text="CertifyMe API key used to authenticate outbound requests.",
    )
    organization_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="CertifyMe organization identifier certificates are issued under.",
    )
    template_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Default CertifyMe certificate template identifier.",
    )

    auto_issue_certificates = models.BooleanField(
        default=False,
        help_text="Automatically issue a CertifyMe certificate when a learner passes a course.",
    )
    auto_issue_badges = models.BooleanField(
        default=False,
        help_text="Automatically issue a CertifyMe badge when a learner passes a course.",
    )

    api_timeout_seconds = models.PositiveIntegerField(
        default=10,
        help_text="Timeout, in seconds, for calls to the CertifyMe API.",
    )
    api_max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Number of automatic retries for failed CertifyMe API calls.",
    )

    class Meta:
        app_label = "openedx_certifyme"
        verbose_name = "CertifyMe Configuration"

    def __str__(self):
        return f"CertifyMeConfiguration(enabled={self.enabled}, api_url={self.api_url!r})"


class CertifyMeCertificate(models.Model):
    """
    Tracks the CertifyMe certificate issued (or attempted) for a single
    (user, course) pair. This is the local system of record that lets us
    render "My Certificates" / instructor tooling without round-tripping
    to CertifyMe on every page view, and gives the retry system
    somewhere to persist failure state between attempts.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ISSUED = "issued", "Issued"
        FAILED = "failed", "Failed"
        REVOKED = "revoked", "Revoked"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="certifyme_certificates",
    )
    course_id = CourseKeyField(max_length=255, db_index=True, case_sensitive=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    certificate_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    verification_url = models.URLField(max_length=255, blank=True, null=True)
    issued_at = models.DateTimeField(blank=True, null=True)

    badge_issued_at = models.DateTimeField(blank=True, null=True)
    badge_response_json = models.JSONField(blank=True, default=dict)

    response_json = models.JSONField(blank=True, default=dict)
    retry_count = models.PositiveIntegerField(default=0)
    failure_reason = models.TextField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "openedx_certifyme"
        verbose_name = "CertifyMe Certificate"
        constraints = [
            models.UniqueConstraint(fields=["user", "course_id"], name="unique_certifyme_certificate_per_user_course")
        ]
        ordering = ["-created"]

    def __str__(self):
        return f"{self.user} / {self.course_id} ({self.status})"
