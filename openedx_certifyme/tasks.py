"""
Celery tasks for the CertifyMe plugin.

All outbound CertifyMe API calls triggered by platform events happen
here, never inline in a Django signal handler or view — this is what
keeps certificate issuance from ever blocking an LMS request. Celery
auto-discovers this module because it's a top-level ``tasks.py`` in an
installed Django app (standard Celery ``autodiscover_tasks()``
behavior); no extra wiring is needed inside edx-platform.

Retry policy: transient failures (``api.RETRYABLE_EXCEPTIONS`` —
connection errors, 5xx, 429) are retried automatically by Celery with
exponential backoff and jitter. Permanent failures (bad API key,
invalid payload, unknown resource) are recorded on the
``CertifyMeCertificate`` row and NOT retried automatically; an operator
can retry them manually from the Django admin or instructor tools,
which simply re-enqueues the same task.
"""

import logging

from celery import shared_task
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey

from openedx_certifyme.api import RETRYABLE_EXCEPTIONS, CertifyMeAPIError, get_api_client
from openedx_certifyme.models import CertifyMeCertificate, CertifyMeConfiguration

logger = logging.getLogger(__name__)

_RETRY_KWARGS = dict(
    bind=True,
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=60,
    retry_backoff_max=3600,
    retry_jitter=True,
    max_retries=5,
    ignore_result=True,
)


@shared_task(**_RETRY_KWARGS)
def issue_certificate_task(self, user_id, course_id_str, recipient_email, recipient_name, course_name):
    """
    Issues (or re-issues, on manual retry) a CertifyMe certificate for
    one learner/course, persisting the outcome on
    ``CertifyMeCertificate``.
    """
    course_key = CourseKey.from_string(course_id_str)

    certificate, _created = CertifyMeCertificate.objects.get_or_create(
        user_id=user_id,
        course_id=course_key,
        defaults={"status": CertifyMeCertificate.Status.PENDING},
    )

    if certificate.status == CertifyMeCertificate.Status.ISSUED:
        logger.info(
            "Certificate already issued for user_id=%s course_id=%s; skipping.", user_id, course_key
        )
        return

    config = CertifyMeConfiguration.current()
    client = get_api_client(config=config)

    try:
        response = client.issue_certificate(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            course_name=course_name,
            course_id=course_key,
            completion_date=timezone.now().isoformat(),
            template_id=config.template_id,
        )
    except RETRYABLE_EXCEPTIONS as exc:
        certificate.status = CertifyMeCertificate.Status.PENDING
        certificate.retry_count = self.request.retries + 1
        certificate.failure_reason = str(exc)
        certificate.save(update_fields=["status", "retry_count", "failure_reason", "modified"])
        logger.warning(
            "Retryable CertifyMe error issuing certificate (attempt %s) user_id=%s course_id=%s: %s",
            self.request.retries + 1,
            user_id,
            course_key,
            exc,
        )
        raise
    except CertifyMeAPIError as exc:
        certificate.status = CertifyMeCertificate.Status.FAILED
        certificate.retry_count = self.request.retries + 1
        certificate.failure_reason = str(exc)
        certificate.save(update_fields=["status", "retry_count", "failure_reason", "modified"])
        logger.error(
            "Permanent CertifyMe error issuing certificate user_id=%s course_id=%s: %s",
            user_id,
            course_key,
            exc,
        )
        return

    certificate.status = CertifyMeCertificate.Status.ISSUED
    certificate.certificate_id = response.get("certificate_id")
    certificate.verification_url = response.get("verification_url")
    certificate.issued_at = timezone.now()
    certificate.response_json = response
    certificate.failure_reason = None
    certificate.save()
    logger.info(
        "Issued CertifyMe certificate %s for user_id=%s course_id=%s",
        certificate.certificate_id,
        user_id,
        course_key,
    )

    if config.auto_issue_badges:
        issue_badge_task.delay(
            user_id=user_id,
            course_id_str=course_id_str,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            course_name=course_name,
        )


@shared_task(**_RETRY_KWARGS)
def issue_badge_task(self, user_id, course_id_str, recipient_email, recipient_name, course_name):
    """Issues a CertifyMe badge, recording the response on the matching certificate row."""
    course_key = CourseKey.from_string(course_id_str)
    config = CertifyMeConfiguration.current()
    client = get_api_client(config=config)

    try:
        response = client.issue_badge(
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            course_name=course_name,
            course_id=course_key,
            template_id=config.template_id,
        )
    except RETRYABLE_EXCEPTIONS:
        logger.warning(
            "Retryable CertifyMe error issuing badge (attempt %s) user_id=%s course_id=%s",
            self.request.retries + 1,
            user_id,
            course_key,
        )
        raise
    except CertifyMeAPIError as exc:
        logger.error(
            "Permanent CertifyMe error issuing badge user_id=%s course_id=%s: %s", user_id, course_key, exc
        )
        return

    CertifyMeCertificate.objects.filter(user_id=user_id, course_id=course_key).update(
        badge_issued_at=timezone.now(), badge_response_json=response
    )
    logger.info("Issued CertifyMe badge for user_id=%s course_id=%s", user_id, course_key)


@shared_task(**_RETRY_KWARGS)
def revoke_certificate_task(self, certificate_pk, reason=None):  # pylint: disable=unused-argument
    """Revokes a previously issued certificate on CertifyMe and marks it revoked locally."""
    certificate = CertifyMeCertificate.objects.get(pk=certificate_pk)
    if not certificate.certificate_id:
        logger.warning(
            "Cannot revoke certificate pk=%s: no CertifyMe certificate_id recorded.", certificate_pk
        )
        return

    client = get_api_client()
    try:
        client.revoke_certificate(certificate.certificate_id, reason=reason)
    except RETRYABLE_EXCEPTIONS:
        raise
    except CertifyMeAPIError as exc:
        logger.error("Failed to revoke CertifyMe certificate %s: %s", certificate.certificate_id, exc)
        return

    certificate.status = CertifyMeCertificate.Status.REVOKED
    certificate.save(update_fields=["status", "modified"])
    logger.info("Revoked CertifyMe certificate %s", certificate.certificate_id)


@shared_task(**_RETRY_KWARGS)
def resend_certificate_email_task(self, certificate_pk):
    """Asks CertifyMe to resend the certificate delivery email to the learner."""
    certificate = CertifyMeCertificate.objects.get(pk=certificate_pk)
    if not certificate.certificate_id:
        logger.warning(
            "Cannot resend email for certificate pk=%s: no CertifyMe certificate_id recorded.",
            certificate_pk,
        )
        return

    client = get_api_client()
    try:
        client.resend_email(certificate.certificate_id)
    except RETRYABLE_EXCEPTIONS:
        raise
    except CertifyMeAPIError as exc:
        logger.error(
            "Failed to resend email for CertifyMe certificate %s: %s", certificate.certificate_id, exc
        )
        return

    logger.info("Resent delivery email for CertifyMe certificate %s", certificate.certificate_id)
