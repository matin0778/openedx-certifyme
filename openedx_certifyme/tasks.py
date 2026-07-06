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
exponential backoff and jitter. Permanent failures (bad API token,
invalid payload, unknown template) are recorded on the
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


def _parse_custom_fields(raw, *, course_name, student_name, student_email, date_str):
    """
    Parses ``CertifyMeConfiguration.custom_fields`` (one ``FieldName=value``
    pair per line) into the ``Custom.FieldName`` payload entries CertifyMe
    expects, substituting ``{course_name}``/``{student_name}``/
    ``{student_email}``/``{date}`` tokens in the value.

    This is the only way course/completion data reaches the credential —
    CertifyMe's API has no dedicated course field (confirmed against its
    own Moodle plugin, which uses this exact same mechanism).
    """
    tokens = {
        "{course_name}": course_name,
        "{student_name}": student_name,
        "{student_email}": student_email,
        "{date}": date_str,
    }

    fields = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue

        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if not name:
            continue

        if name.startswith("Custom."):
            name = name[len("Custom."):]
        name = f"Custom.{name}"

        for token, replacement in tokens.items():
            value = value.replace(token, str(replacement))
        fields[name] = value

    return fields


@shared_task(**_RETRY_KWARGS)
def issue_certificate_task(self, user_id, course_id_str, recipient_email, recipient_name, course_name):
    """
    Issues (or re-issues, on manual retry) a CertifyMe credential for
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

    custom_fields = _parse_custom_fields(
        config.custom_fields,
        course_name=course_name,
        student_name=recipient_name,
        student_email=recipient_email,
        date_str=timezone.now().strftime("%d %b %Y"),
    )

    try:
        response = client.issue_credential(
            name=recipient_name,
            email=recipient_email,
            template_id=config.template_id,
            text=config.text,
            verify_mode=config.verify_mode,
            verify_code=config.verify_code,
            license_number=config.license_number,
            custom_fields=custom_fields,
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
    certificate.certificate_id = response.get("credential_UID")
    certificate.verification_url = response.get("credential_url") or response.get("credential_customURL")
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


@shared_task(bind=True, ignore_result=True)
def bulk_issue_certificates_task(self, course_id_str):  # pylint: disable=unused-argument
    """
    Fans out to :func:`issue_certificate_task` for every actively
    enrolled, passing learner in the course who doesn't already have an
    issued certificate.

    Grade computation (``CourseGradeFactory``) happens here, in the
    background, rather than in the instructor's request — bulk-issuing
    for a large cohort can take a while and must never tie up a web
    worker. ``CourseEnrollment`` and ``CourseGradeFactory`` are
    edx-platform internals, imported locally since this task only ever
    runs inside edx-platform.
    """
    from common.djangoapps.student.models import CourseEnrollment
    from lms.djangoapps.grades.course_grade_factory import CourseGradeFactory

    course_key = CourseKey.from_string(course_id_str)

    already_issued_user_ids = set(
        CertifyMeCertificate.objects.filter(
            course_id=course_key, status=CertifyMeCertificate.Status.ISSUED
        ).values_list("user_id", flat=True)
    )

    queued = 0
    enrollments = CourseEnrollment.objects.filter(course_id=course_key, is_active=True).select_related("user")
    for enrollment in enrollments:
        user = enrollment.user
        if user.id in already_issued_user_ids:
            continue

        grade = CourseGradeFactory().read(user, course_key=course_key)
        if not grade or not grade.passed:
            continue

        issue_certificate_task.delay(
            user_id=user.id,
            course_id_str=course_id_str,
            recipient_email=user.email,
            recipient_name=user.get_full_name() or user.username,
            course_name=str(course_key),
        )
        queued += 1

    logger.info("Bulk issuance for course_id=%s queued %d certificate(s)", course_key, queued)
