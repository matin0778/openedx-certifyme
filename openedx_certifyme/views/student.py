"""
Learner-facing certificate views.

The real Open edX student dashboard (``/dashboard``) is an edx-platform
core template with no clean plugin-injection point for a third-party
"My Certificates" section (that only exists for the newer React MFEs,
a separate frontend project). Rather than patch core templates, this
plugin serves its own lightweight, self-contained page under
``/certifyme/certificates/``.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from openedx_certifyme.models import CertifyMeCertificate
from openedx_certifyme.views._utils import get_course_display_name

logger = logging.getLogger(__name__)


@login_required
def my_certificates(request):
    """Lists the logged-in learner's CertifyMe certificates."""
    certificates = CertifyMeCertificate.objects.filter(user=request.user).order_by("-created")
    rows = [
        {"certificate": certificate, "course_display_name": get_course_display_name(certificate.course_id)}
        for certificate in certificates
    ]
    logger.info("Rendering My Certificates for user_id=%s (%d rows)", request.user.id, len(rows))
    return render(request, "openedx_certifyme/my_certificates.html", {"rows": rows})


def verify_certificate(request, pk):
    """
    Public certificate verification page.

    Deliberately unauthenticated: a certificate's purpose is to be
    verifiable by a third party (e.g. an employer) who has the link but
    no platform account. This only confirms our own local issuance
    record — CertifyMe's API has no confirmed status-check endpoint to
    round-trip against (see ``api.py``'s module docstring), so there is
    no live check here.
    """
    certificate = get_object_or_404(CertifyMeCertificate, pk=pk)

    return render(
        request,
        "openedx_certifyme/verify_certificate.html",
        {
            "certificate": certificate,
            "course_display_name": get_course_display_name(certificate.course_id),
        },
    )
