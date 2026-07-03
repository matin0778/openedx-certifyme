import logging

from django.conf import settings
from django.http import JsonResponse

from openedx_certifyme import __version__

logger = logging.getLogger(__name__)


def health(request):
    """
    Liveness probe confirming the plugin is installed, discovered by the
    Open edX plugin architecture, and its urlconf is mounted.
    """
    # DEBUG, not INFO: liveness probes hit this every few seconds in
    # production and would otherwise flood the log at normal verbosity.
    logger.debug("CertifyMe health check requested.")
    return JsonResponse(
        {
            "plugin": "openedx-certifyme",
            "status": "ok",
            "version": __version__,
            "enabled": getattr(settings, "CERTIFYME_ENABLED", False),
        }
    )
