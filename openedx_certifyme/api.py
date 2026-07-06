"""
REST API client for CertifyMe.

This is the *only* module in the plugin that talks to CertifyMe over
HTTP — everything else (signals, tasks, views, admin) goes through
:func:`get_api_client` / :class:`CertifyMeAPIClient`.

.. important::
   The endpoint, auth scheme, and payload/response shape below are
   confirmed against a real, successful live call (not a guess):

   - The working endpoint is the regional one (e.g.
     ``POST https://apac.platform.certifyme.dev/api/v2/credential``),
     matching CertifyMe's own Moodle plugin (``local_certifyme``) — the
     generic ``https://my.certifyme.online/api/v2/credential`` shown in
     CertifyMe's public API reference consistently 500'd in testing.
   - Auth is the raw API token in the ``Authorization`` header, with no
     ``Bearer`` prefix.
   - ``template_ID`` must be sent as a JSON number, not a string — a
     string value against the working regional endpoint was not
     separately isolated, but the one confirmed-successful request used
     a bare integer, matching CertifyMe's own internal Postman example.
   - The response body **does** carry a stable id and verification URL
     — confirmed via a real successful call, returning (among other
     fields) ``credential_UID`` and ``credential_url``. CertifyMe's own
     Moodle plugin never reads these (it only checks HTTP status), but
     they're real and this client captures them.
   - No separate badge-issuance endpoint is known to exist. CertifyMe's
     public API reference does list ``GET``/``PUT``/``DELETE`` by
     credential id — not yet implemented here, only single-credential
     issuance.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from openedx_certifyme import servers

logger = logging.getLogger(__name__)


class CertifyMeAPIError(Exception):
    """Base exception for all CertifyMe API failures."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class CertifyMeConnectionError(CertifyMeAPIError):
    """Network-level failure (DNS, timeout, refused connection, etc). Retryable."""


class CertifyMeServerError(CertifyMeAPIError):
    """CertifyMe returned a 5xx after exhausting connection-level retries. Retryable."""


class CertifyMeRateLimitError(CertifyMeServerError):
    """CertifyMe returned 429. Retryable."""


class CertifyMeAuthenticationError(CertifyMeAPIError):
    """CertifyMe rejected the configured API token (401/403). Not retryable."""


class CertifyMeNotFoundError(CertifyMeAPIError):
    """CertifyMe returned 404 — e.g. the configured template ID doesn't exist on this server. Not retryable."""


class CertifyMeValidationError(CertifyMeAPIError):
    """CertifyMe rejected the request payload (400/422). Not retryable."""


class CertifyMeNotConfiguredError(CertifyMeAPIError):
    """No usable CertifyMe configuration (missing API token) exists yet. Not retryable."""


#: Exceptions that represent a transient failure worth automatically retrying.
RETRYABLE_EXCEPTIONS = (CertifyMeConnectionError, CertifyMeServerError, CertifyMeRateLimitError)


class CertifyMeAPIClient:
    """
    Thin, retrying HTTP client for CertifyMe's credential-issuance API.

    Handles authentication, timeouts, connection-level retries with
    backoff, response-status mapping to typed exceptions, and logging.
    Application-level retry policy (Celery backoff) lives in
    :mod:`openedx_certifyme.tasks`, not here — this class only retries
    at the HTTP transport layer (e.g. a dropped connection).
    """

    def __init__(self, server, api_token, timeout=10, max_retries=3):
        if not api_token:
            raise CertifyMeNotConfiguredError(
                "CertifyMe is not configured yet: an API token is required."
            )

        self.url = servers.endpoint(server)
        self.timeout = timeout

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "Authorization": api_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # -- internals ---------------------------------------------------

    @staticmethod
    def _safe_body(response):
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _request(self, method, **kwargs):
        logger.info("CertifyMe API request starting: %s %s", method, self.url)
        try:
            response = self.session.request(method, self.url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            logger.warning("CertifyMe API connection error: %s %s -> %s", method, self.url, exc)
            raise CertifyMeConnectionError(f"Could not reach CertifyMe API: {exc}") from exc

        logger.info(
            "CertifyMe API request finished: %s %s -> HTTP %s",
            method,
            self.url,
            response.status_code,
        )
        body = self._safe_body(response)

        if response.status_code in (401, 403):
            raise CertifyMeAuthenticationError(
                "CertifyMe API rejected the configured API token.",
                status_code=response.status_code,
                response_body=body,
            )
        if response.status_code == 404:
            raise CertifyMeNotFoundError(
                "CertifyMe returned 404 — check the configured template ID exists on this server.",
                status_code=response.status_code,
                response_body=body,
            )
        if response.status_code == 429:
            raise CertifyMeRateLimitError(
                "CertifyMe API rate limit exceeded.", status_code=response.status_code, response_body=body
            )
        if response.status_code in (400, 422):
            raise CertifyMeValidationError(
                "CertifyMe API rejected the request payload.",
                status_code=response.status_code,
                response_body=body,
            )
        if response.status_code >= 500:
            raise CertifyMeServerError(
                "CertifyMe API returned a server error.", status_code=response.status_code, response_body=body
            )
        if response.status_code >= 400:
            raise CertifyMeAPIError(
                f"CertifyMe API returned unexpected status {response.status_code}.",
                status_code=response.status_code,
                response_body=body,
            )

        return body

    # -- public API ---------------------------------------------------

    def issue_credential(
        self,
        *,
        name,
        email,
        template_id,
        text="",
        verify_mode="None",
        verify_code=None,
        license_number=None,
        custom_fields=None,
    ):
        """
        Issues a CertifyMe credential. Returns the raw CertifyMe response
        body, confirmed (via a real successful call) to include at least
        ``credential_UID`` (stable credential id) and ``credential_url`` /
        ``credential_customURL`` (public verification link), alongside
        echoed-back fields like ``credential_name``/``credential_email``.
        """
        try:
            template_id = int(template_id)
        except (TypeError, ValueError):
            pass

        payload = {
            "name": name,
            "email": email,
            "template_ID": template_id,
            "text": text or "",
            "verify_mode": verify_mode or "None",
        }
        if verify_code:
            payload["verify_code"] = verify_code
        if license_number:
            payload["license_number"] = license_number
        if custom_fields:
            payload.update(custom_fields)

        return self._request("POST", json=payload)


def get_api_client(config=None):
    """
    Builds a :class:`CertifyMeAPIClient` from ``CertifyMeConfiguration``.

    Accepts an explicit ``config`` (a ``CertifyMeConfiguration`` instance)
    so callers that already fetched one (e.g. an admin action operating
    on a specific row) don't trigger a second lookup; otherwise falls
    back to the cached current configuration.
    """
    from openedx_certifyme.models import CertifyMeConfiguration

    config = config or CertifyMeConfiguration.current()
    return CertifyMeAPIClient(
        server=config.server,
        api_token=config.api_token,
        timeout=config.api_timeout_seconds,
        max_retries=config.api_max_retries,
    )
