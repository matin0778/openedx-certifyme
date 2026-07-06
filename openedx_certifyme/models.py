"""
Database models for the CertifyMe plugin.

``CertifyMeConfiguration`` is a `ConfigurationModel`_, the standard Open
edX extension point for admin-editable, versioned configuration
(``enabled`` toggle, automatic change history, cached ``.current()``
lookup) — used throughout edx-platform (e.g. certificate generation,
programs, credentials configs). We reuse it instead of hand-rolling a
settings table + caching layer.

Field names and semantics here follow CertifyMe's real
``POST /api/v2/credential`` contract, confirmed against CertifyMe's own
Moodle plugin (``local_certifyme``) — the only working reference
implementation available. There is no organization-id concept and no
per-course field in that contract: an account is scoped entirely by
its API token + regional server, and any course/completion data has to
be threaded through ``custom_fields`` (see below).

.. _ConfigurationModel: https://github.com/openedx/django-config-models
"""

from config_models.models import ConfigurationModel
from django.conf import settings
from django.db import models
from opaque_keys.edx.django.models import CourseKeyField

from openedx_certifyme import servers


class CertifyMeConfiguration(ConfigurationModel):
    """
    Admin-editable configuration for the CertifyMe integration.

    Every save creates a new row (``ConfigurationModel`` semantics), so
    changes are fully auditable via the Django admin history view.
    ``CertifyMeConfiguration.current()`` returns the latest entry.
    """

    VERIFY_MODE_CHOICES = [
        ("None", "None"),
        ("SSN", "SSN"),
        ("Code", "Code"),
        ("Passport Number", "Passport Number"),
    ]

    server = models.CharField(
        max_length=20,
        choices=servers.choices(),
        default=servers.DEFAULT_SERVER,
        help_text="Which CertifyMe regional server this account is provisioned on.",
    )
    api_token = models.CharField(
        max_length=255,
        blank=True,
        help_text="CertifyMe API token, sent as-is in the Authorization header (no 'Bearer' prefix).",
    )
    template_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="CertifyMe credential template ID.",
    )

    text = models.CharField(
        max_length=255,
        blank=True,
        help_text="Free-text label shown on the credential (e.g. job title, organization).",
    )
    verify_mode = models.CharField(
        max_length=20,
        choices=VERIFY_MODE_CHOICES,
        default="None",
        help_text="Identity-verification mode to attach to the credential.",
    )
    verify_code = models.CharField(
        max_length=255,
        blank=True,
        help_text="Verification code/number. Required by CertifyMe when verify_mode is not 'None'.",
    )
    license_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional license number to display on the credential.",
    )
    custom_fields = models.TextField(
        blank=True,
        help_text=(
            "One 'FieldName=value' pair per line, sent as 'Custom.FieldName' in the API "
            "payload — this is the only way to get course/completion data onto the "
            "credential, since CertifyMe's API has no dedicated course field. Supports "
            "{course_name}, {student_name}, {student_email}, {date} tokens, e.g.: "
            "Course={course_name}"
        ),
    )

    auto_issue_certificates = models.BooleanField(
        default=False,
        help_text="Automatically issue a CertifyMe certificate when a learner passes a course.",
    )

    api_timeout_seconds = models.PositiveIntegerField(
        default=30,
        help_text=(
            "Timeout, in seconds, for calls to the CertifyMe API. Issuance calls have been "
            "observed taking ~20s (likely generating/uploading the credential image), so this "
            "must stay comfortably above that."
        ),
    )
    api_max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Number of automatic retries for failed CertifyMe API calls.",
    )

    class Meta:
        app_label = "openedx_certifyme"
        verbose_name = "CertifyMe Configuration"

    def __str__(self):
        return f"CertifyMeConfiguration(enabled={self.enabled}, server={self.server!r})"


class CertifyMeCertificate(models.Model):
    """
    Tracks the CertifyMe credential issued (or attempted) for a single
    (user, course) pair. This is the local system of record that lets us
    render "My Certificates" / instructor tooling without round-tripping
    to CertifyMe on every page view, and gives the retry system
    somewhere to persist failure state between attempts.

    CertifyMe's ``POST /api/v2/credential`` response is confirmed (via a
    real successful call) to carry a stable ``credential_UID`` and a
    ``credential_url`` verification link — stored here as
    ``certificate_id`` and ``verification_url``.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ISSUED = "issued", "Issued"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="certifyme_certificates",
    )
    course_id = CourseKeyField(max_length=255, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    certificate_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    verification_url = models.URLField(max_length=255, blank=True, null=True)
    issued_at = models.DateTimeField(blank=True, null=True)

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
