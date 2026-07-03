"""
Common (base) settings for the CertifyMe plugin.

Injected into the LMS/CMS Django settings by the Open edX plugin
architecture (see ``plugin_app`` in ``openedx_certifyme.apps``). Values
here are safe defaults; real deployment values are supplied via Tutor
env config and picked up in ``production.py``, and later overridden at
runtime by the admin-configurable model (Phase 3).
"""


def plugin_settings(settings):
    settings.CERTIFYME_ENABLED = False

    settings.CERTIFYME_API_URL = ""
    settings.CERTIFYME_API_KEY = ""
    settings.CERTIFYME_ORGANIZATION_ID = ""
    settings.CERTIFYME_TEMPLATE_ID = ""

    settings.CERTIFYME_AUTO_ISSUE_CERTIFICATES = False
    settings.CERTIFYME_AUTO_ISSUE_BADGES = False

    settings.CERTIFYME_API_TIMEOUT_SECONDS = 10
    settings.CERTIFYME_API_MAX_RETRIES = 3
