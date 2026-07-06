"""
Single source of truth for CertifyMe's regional API servers.

Mirrors the ``classes/servers.php`` file from CertifyMe's own Moodle
plugin (``local_certifyme``), the only confirmed-working reference
implementation available for this integration. CertifyMe accounts are
provisioned on exactly one of these regional servers; the admin picks
the right one for their account from ``CertifyMeConfiguration.server``.

To add a new server, only add an entry here — the admin form choices
and API routing both read from this module.
"""

SERVERS = {
    "apac": {
        "label": "APAC (https://apac.platform.certifyme.dev)",
        "url": "https://apac.platform.certifyme.dev/api/v2/credential",
    },
    "eu2": {
        "label": "EU2 (https://eu2.certifyme.org)",
        "url": "https://eu2.certifyme.org/api/v2/credential",
    },
    "us1": {
        "label": "US1 (https://us1.certifyme.org)",
        "url": "https://us1.certifyme.org/api/v2/credential",
    },
    "butterfly": {
        "label": "Butterfly (https://butterfly.certifyme.org)",
        "url": "https://butterfly.certifyme.org/api/v2/credential",
    },
}

DEFAULT_SERVER = "apac"


def choices():
    """Returns ``(key, label)`` pairs for use as a Django field's ``choices``."""
    return [(key, server["label"]) for key, server in SERVERS.items()]


def endpoint(server_key):
    """Returns the credential-issuance URL for a server key, falling back to the default."""
    server = SERVERS.get(server_key, SERVERS[DEFAULT_SERVER])
    return server["url"]
