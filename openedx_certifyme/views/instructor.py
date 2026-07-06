"""
Course-staff tooling for CertifyMe certificate management.

Like the learner-facing pages, this is a standalone page under
``/certifyme/instructor/<course_id>/`` rather than an injected tab in
the legacy instructor dashboard, which has no supported third-party
extension point without patching edx-platform core templates.

Every mutating action (issue/bulk-issue/retry) enqueues a Celery task
and redirects immediately — nothing here calls the CertifyMe API
inline, so an instructor bulk-issuing certificates for a large cohort
never ties up a web worker.

There is no revoke/resend action: CertifyMe's API has no confirmed
endpoint for either (see ``api.py``'s module docstring).
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey

from openedx_certifyme.models import CertifyMeCertificate
from openedx_certifyme.views._utils import get_course_display_name

logger = logging.getLogger(__name__)

User = get_user_model()


def _parse_course_key(course_id):
    try:
        return CourseKey.from_string(course_id)
    except InvalidKeyError as exc:
        raise Http404("Invalid course id.") from exc


def _require_course_staff(request, course_key):
    """
    Course staff/instructor check, matching the access control used
    throughout edx-platform's own instructor-only views.
    """
    if request.user.is_staff:
        return

    from common.djangoapps.student.roles import CourseInstructorRole, CourseStaffRole

    if CourseStaffRole(course_key).has_user(request.user) or CourseInstructorRole(course_key).has_user(
        request.user
    ):
        return
    raise PermissionDenied("You do not have course staff access to CertifyMe tools for this course.")


@login_required
def course_certificates(request, course_id):
    """Search/filter list of every CertifyMe certificate for a course."""
    course_key = _parse_course_key(course_id)
    _require_course_staff(request, course_key)

    certificates = CertifyMeCertificate.objects.filter(course_id=course_key).select_related("user")

    status_filter = request.GET.get("status", "")
    if status_filter:
        certificates = certificates.filter(status=status_filter)

    query = request.GET.get("q", "").strip()
    if query:
        certificates = certificates.filter(Q(user__username__icontains=query) | Q(user__email__icontains=query))

    certificates = certificates.order_by("-created")

    return render(
        request,
        "openedx_certifyme/instructor_tools.html",
        {
            "course_id": course_id,
            "course_display_name": get_course_display_name(course_key),
            "certificates": certificates,
            "status_choices": CertifyMeCertificate.Status.choices,
            "status_filter": status_filter,
            "query": query,
        },
    )


@login_required
def issue_certificate_for_user(request, course_id):
    """Manually issues a certificate for one learner, by username or email."""
    course_key = _parse_course_key(course_id)
    _require_course_staff(request, course_key)
    if request.method != "POST":
        raise Http404()

    identifier = request.POST.get("user_identifier", "").strip()
    user = User.objects.filter(Q(username=identifier) | Q(email=identifier)).first()
    if not user:
        logger.warning(
            "CertifyMe manual issue: no user found for identifier=%r course_id=%s", identifier, course_key
        )
        return redirect(f"{reverse('certifyme:instructor-course-certificates', args=[course_id])}?error=user_not_found")

    from openedx_certifyme.tasks import issue_certificate_task

    issue_certificate_task.delay(
        user_id=user.id,
        course_id_str=str(course_key),
        recipient_email=user.email,
        recipient_name=user.get_full_name() or user.username,
        course_name=get_course_display_name(course_key),
    )
    logger.info(
        "Instructor user_id=%s queued manual issuance for user_id=%s course_id=%s",
        request.user.id,
        user.id,
        course_key,
    )
    return redirect(reverse("certifyme:instructor-course-certificates", args=[course_id]))


@login_required
def bulk_issue_certificates(request, course_id):
    """Queues issuance for every actively-enrolled, passing learner without an issued certificate."""
    course_key = _parse_course_key(course_id)
    _require_course_staff(request, course_key)
    if request.method != "POST":
        raise Http404()

    from openedx_certifyme.tasks import bulk_issue_certificates_task

    bulk_issue_certificates_task.delay(course_id_str=str(course_key))
    logger.info("Instructor user_id=%s queued bulk issuance for course_id=%s", request.user.id, course_key)
    return redirect(reverse("certifyme:instructor-course-certificates", args=[course_id]))


@login_required
def retry_certificate(request, course_id, pk):
    """Re-queues issuance for a single certificate (typically one in FAILED status)."""
    course_key = _parse_course_key(course_id)
    _require_course_staff(request, course_key)
    certificate = get_object_or_404(CertifyMeCertificate, pk=pk, course_id=course_key)
    if request.method != "POST":
        raise Http404()

    from openedx_certifyme.tasks import issue_certificate_task

    issue_certificate_task.delay(
        user_id=certificate.user_id,
        course_id_str=str(course_key),
        recipient_email=certificate.user.email,
        recipient_name=certificate.user.get_full_name() or certificate.user.username,
        course_name=get_course_display_name(course_key),
    )
    logger.info("Instructor user_id=%s queued retry for certificate pk=%s", request.user.id, pk)
    return redirect(reverse("certifyme:instructor-course-certificates", args=[course_id]))


@login_required
def retry_failed_certificates(request, course_id):
    """Re-queues issuance for every FAILED certificate in the course."""
    course_key = _parse_course_key(course_id)
    _require_course_staff(request, course_key)
    if request.method != "POST":
        raise Http404()

    from openedx_certifyme.tasks import issue_certificate_task

    failed = list(
        CertifyMeCertificate.objects.filter(
            course_id=course_key, status=CertifyMeCertificate.Status.FAILED
        ).select_related("user")
    )
    for certificate in failed:
        issue_certificate_task.delay(
            user_id=certificate.user_id,
            course_id_str=str(course_key),
            recipient_email=certificate.user.email,
            recipient_name=certificate.user.get_full_name() or certificate.user.username,
            course_name=get_course_display_name(course_key),
        )
    logger.info(
        "Instructor user_id=%s queued retry for %d failed certificates in course_id=%s",
        request.user.id,
        len(failed),
        course_key,
    )
    return redirect(reverse("certifyme:instructor-course-certificates", args=[course_id]))
