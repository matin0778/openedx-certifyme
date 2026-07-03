"""
AppConfig for the CertifyMe plugin.

Registration uses the Open edX Django plugin architecture
(``openedx.core.djangoapps.plugins``): the ``plugin_app`` dict below is
read by edx-platform at startup, once this package's entry points
(declared in ``setup.py``) are discovered via
``importlib.metadata.entry_points``. Through it edx-platform:

- mounts ``urls.py`` under ``/certifyme/`` in the LMS/CMS root urlconf
  (``url_config``), and
- calls ``plugin_settings(settings)`` from ``settings/common.py`` and
  ``settings/production.py`` for each service (``settings_config``).

No changes to edx-platform core or manual ``INSTALLED_APPS`` edits are
required.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CertifyMeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"

    name = "openedx_certifyme"
    verbose_name = "CertifyMe Certificate Integration"

    plugin_app = {
        "url_config": {
            "lms.djangoapp": {
                "namespace": "certifyme",
                "regex": r"^certifyme/",
                "relative_path": "urls",
            },
        },
        "settings_config": {
            "lms.djangoapp": {
                "common": {"relative_path": "settings.common"},
                "production": {"relative_path": "settings.production"},
            },
            "cms.djangoapp": {
                "common": {"relative_path": "settings.common"},
                "production": {"relative_path": "settings.production"},
            },
        },
    }

    def ready(self):
        from openedx_certifyme import signals  # noqa: F401  pylint: disable=unused-import

        logger.info(
            "CertifyMe plugin loaded (app=%s, verbose_name=%s).",
            self.name,
            self.verbose_name,
        )
