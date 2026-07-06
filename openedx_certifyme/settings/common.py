"""
Common (base) settings for the CertifyMe plugin.

Injected into the LMS/CMS Django settings by the Open edX plugin
architecture (see ``plugin_app`` in ``openedx_certifyme.apps``).

All real configuration (server, API token, template id, etc.) lives in
the admin-editable ``CertifyMeConfiguration`` model, not in Django
settings — ``CERTIFYME_ENABLED`` here is only a static default read by
the health check view before any configuration row exists.
"""


def plugin_settings(settings):
    settings.CERTIFYME_ENABLED = False
