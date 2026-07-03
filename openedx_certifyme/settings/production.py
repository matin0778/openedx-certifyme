"""
Production settings for the CertifyMe plugin.

Reads deployment-specific values out of the standard Open edX
``ENV_TOKENS`` / ``AUTH_TOKENS`` dictionaries, which Tutor populates from
``config.yml`` into ``lms.env.yml`` / ``lms.auth.yml`` at image build
time. This keeps secrets (the API key) out of version control and out
of ``common.py``.
"""


def plugin_settings(settings):
    env_tokens = getattr(settings, "ENV_TOKENS", {})
    auth_tokens = getattr(settings, "AUTH_TOKENS", {})

    settings.CERTIFYME_ENABLED = env_tokens.get(
        "CERTIFYME_ENABLED", settings.CERTIFYME_ENABLED
    )

    settings.CERTIFYME_API_URL = env_tokens.get(
        "CERTIFYME_API_URL", settings.CERTIFYME_API_URL
    )
    settings.CERTIFYME_API_KEY = auth_tokens.get(
        "CERTIFYME_API_KEY", settings.CERTIFYME_API_KEY
    )
    settings.CERTIFYME_ORGANIZATION_ID = env_tokens.get(
        "CERTIFYME_ORGANIZATION_ID", settings.CERTIFYME_ORGANIZATION_ID
    )
    settings.CERTIFYME_TEMPLATE_ID = env_tokens.get(
        "CERTIFYME_TEMPLATE_ID", settings.CERTIFYME_TEMPLATE_ID
    )

    settings.CERTIFYME_AUTO_ISSUE_CERTIFICATES = env_tokens.get(
        "CERTIFYME_AUTO_ISSUE_CERTIFICATES",
        settings.CERTIFYME_AUTO_ISSUE_CERTIFICATES,
    )
    settings.CERTIFYME_AUTO_ISSUE_BADGES = env_tokens.get(
        "CERTIFYME_AUTO_ISSUE_BADGES", settings.CERTIFYME_AUTO_ISSUE_BADGES
    )

    settings.CERTIFYME_API_TIMEOUT_SECONDS = env_tokens.get(
        "CERTIFYME_API_TIMEOUT_SECONDS", settings.CERTIFYME_API_TIMEOUT_SECONDS
    )
    settings.CERTIFYME_API_MAX_RETRIES = env_tokens.get(
        "CERTIFYME_API_MAX_RETRIES", settings.CERTIFYME_API_MAX_RETRIES
    )
