"""
Production settings for the CertifyMe plugin.

Reads deployment-specific values out of the standard Open edX
``ENV_TOKENS`` dictionary, which Tutor populates from ``config.yml``
into ``lms.env.yml`` at image build time.

All real configuration (server, API token, template id, etc.) lives in
the admin-editable ``CertifyMeConfiguration`` model, not in Django
settings — ``CERTIFYME_ENABLED`` here is only a static default read by
the health check view before any configuration row exists.
"""


def plugin_settings(settings):
    env_tokens = getattr(settings, "ENV_TOKENS", {})

    settings.CERTIFYME_ENABLED = env_tokens.get(
        "CERTIFYME_ENABLED", settings.CERTIFYME_ENABLED
    )
