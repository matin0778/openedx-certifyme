"""
REST API client for CertifyMe.

This is the *only* module in the plugin that talks to CertifyMe over
HTTP — everything else (signals, tasks, views, admin) goes through
:func:`get_api_client` / :class:`CertifyMeAPIClient`.

.. important::
   CertifyMe's exact API contract was not provided to this project, so
   the endpoint paths and JSON payload shapes below follow common REST
   conventions (Bearer auth, ``/api/v1/...`` resource paths, a flat
   JSON body per call). They are centralized as class constants
   (``CERTIFICATES_ENDPOINT``, ``BADGES_ENDPOINT``, ``PING_ENDPOINT``)
   and small ``_build_*_payload`` helpers specifically so they are a
   one-place edit once you have CertifyMe's real OpenAPI reference.
"""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    """CertifyMe rejected the configured API key (401/403). Not retryable."""


class CertifyMeNotFoundError(CertifyMeAPIError):
    """The requested certificate/badge does not exist on CertifyMe (404). Not retryable."""


class CertifyMeValidationError(CertifyMeAPIError):
    """CertifyMe rejected the request payload (400/422). Not retryable."""


#: Exceptions that represent a transient failure worth automatically retrying.
RETRYABLE_EXCEPTIONS = (CertifyMeConnectionError, CertifyMeServerError, CertifyMeRateLimitError)


class CertifyMeAPIClient:
    """
    Thin, retrying HTTP client for the CertifyMe REST API.

    Handles authentication, timeouts, connection-level retries with
    backoff, response-status mapping to typed exceptions, and logging.
    Application-level retry policy (Celery backoff) lives in
    :mod:`openedx_certifyme.tasks`, not here — this class only retries
    at the HTTP transport layer (e.g. a dropped connection).
    """

    CERTIFICATES_ENDPOINT = "api/v1/certificates"
    BADGES_ENDPOINT = "api/v1/badges"
    PING_ENDPOINT = "api/v1/ping"

    def __init__(self, api_url, api_key, organization_id="", timeout=10, max_retries=3):
        if not api_url:
            raise ValueError("CertifyMe api_url is required to build an API client.")
        if not api_key:
            raise ValueError("CertifyMe api_key is required to build an API client.")

        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.organization_id = organization_id
        self.timeout = timeout

        self.session = requests.Session()
        retry = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST", "PATCH", "DELETE"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # -- internals ---------------------------------------------------

    def _url(self, path):
        return f"{self.api_url}/{path.lstrip('/')}"

    @staticmethod
    def _safe_body(response):
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _request(self, method, path, **kwargs):
        url = self._url(path)
        logger.info("CertifyMe API request starting: %s %s", method, url)
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            logger.warning("CertifyMe API connection error: %s %s -> %s", method, url, exc)
            raise CertifyMeConnectionError(f"Could not reach CertifyMe API: {exc}") from exc

        logger.info(
            "CertifyMe API request finished: %s %s -> HTTP %s",
            method,
            url,
            response.status_code,
        )
        body = self._safe_body(response)

        if response.status_code in (401, 403):
            raise CertifyMeAuthenticationError(
                "CertifyMe API rejected the configured API key.",
                status_code=response.status_code,
                response_body=body,
            )
        if response.status_code == 404:
            raise CertifyMeNotFoundError(
                "CertifyMe resource not found.", status_code=response.status_code, response_body=body
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

    def test_connection(self):
        """
        Round-trips a lightweight request to confirm the configured URL
        and API key are valid. Raises ``CertifyMeAPIError`` (or a
        subclass) on failure.
        """
        body = self._request("GET", self.PING_ENDPOINT)
        return {"success": True, "response": body}

    def issue_certificate(
        self,
        *,
        recipient_email,
        recipient_name,
        course_name,
        course_id,
        completion_date,
        template_id=None,
    ):
        """
        Issues a certificate. ``completion_date`` must be an ISO-8601
        string. Returns the raw CertifyMe response (expected to include
        a certificate id and verification URL).
        """
        payload = {
            "organization_id": self.organization_id,
            "template_id": template_id or "",
            "recipient": {"email": recipient_email, "name": recipient_name},
            "course": {"id": str(course_id), "name": course_name},
            "completion_date": completion_date,
        }
        return self._request("POST", f"{self.CERTIFICATES_ENDPOINT}/issue", json=payload)

    def issue_badge(self, *, recipient_email, recipient_name, course_name, course_id, template_id=None):
        """Issues a badge. Returns the raw CertifyMe response."""
        payload = {
            "organization_id": self.organization_id,
            "template_id": template_id or "",
            "recipient": {"email": recipient_email, "name": recipient_name},
            "course": {"id": str(course_id), "name": course_name},
        }
        return self._request("POST", f"{self.BADGES_ENDPOINT}/issue", json=payload)

    def revoke_certificate(self, certificate_id, reason=None):
        """Revokes a previously issued certificate."""
        payload = {"reason": reason or ""}
        return self._request("POST", f"{self.CERTIFICATES_ENDPOINT}/{certificate_id}/revoke", json=payload)

    def resend_email(self, certificate_id):
        """Asks CertifyMe to resend the certificate delivery email."""
        return self._request("POST", f"{self.CERTIFICATES_ENDPOINT}/{certificate_id}/resend")

    def get_certificate(self, certificate_id):
        """Fetches the current state of a certificate from CertifyMe."""
        return self._request("GET", f"{self.CERTIFICATES_ENDPOINT}/{certificate_id}")


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
        api_url=config.api_url,
        api_key=config.api_key,
        organization_id=config.organization_id,
        timeout=config.api_timeout_seconds,
        max_retries=config.api_max_retries,
    )
