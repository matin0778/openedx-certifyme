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
from django.db import models


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
