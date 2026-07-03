"""Small helpers shared across the CertifyMe views."""

import logging

logger = logging.getLogger(__name__)


def get_course_display_name(course_key):
    """
    Best-effort course title lookup for display purposes only.

    ``CourseOverview`` is an edx-platform-internal model (this plugin
    only ever runs inside edx-platform, so importing it here is safe,
    but it can't be installed in a standalone test environment, and the
    course itself may have been deleted since the certificate was
    issued) — either way, falling back to the raw course id is fine
    since this value is never used for anything but display.
    """
    try:
        from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
    except ImportError:
        return str(course_key)

    try:
        return CourseOverview.get_from_id(course_key).display_name or str(course_key)
    except Exception:  # pylint: disable=broad-except
        logger.debug("Could not resolve display name for course_id=%s", course_key)
        return str(course_key)
