"""
Listens for the course-completion event and, if enabled, kicks off
certificate issuance.

Subscribes to ``openedx_events.learning.signals.COURSE_PASSING_STATUS_UPDATED``
— the Open edX Hooks Extension Framework event edx-platform's own grading
app emits whenever a learner's passing status changes (this is the same
category of signal edx-platform's own badges app has historically used
for "award something when the learner passes"). We use this modern,
decoupled event bus signal rather than reaching into grades/certificates
internals directly.

The exact event payload (``CoursePassingStatusData``) was verified
against ``openedx-events`` directly: it carries ``is_passing`` (bool),
``course`` (``course_key``, ``display_name``), and ``user`` (``id``,
``pii.username``, ``pii.email``, ``pii.name``). Event payloads have
changed across Open edX releases before, so this handler logs the raw
event and fails closed (logs + returns) rather than raising if a field
is ever missing, instead of crashing grade processing for every learner.
"""

import logging

from django.dispatch import receiver
from openedx_events.learning.signals import COURSE_PASSING_STATUS_UPDATED

from openedx_certifyme.models import CertifyMeConfiguration

logger = logging.getLogger(__name__)


@receiver(COURSE_PASSING_STATUS_UPDATED)
def handle_course_passing_status_updated(sender, signal, **kwargs):  # pylint: disable=unused-argument
    event_data = kwargs.get("course_passing_status")
    if event_data is None:
        logger.warning(
            "COURSE_PASSING_STATUS_UPDATED received with no course_passing_status payload: %s",
            kwargs,
        )
        return

    try:
        is_passing = event_data.is_passing
        course_key = event_data.course.course_key
        course_name = event_data.course.display_name or str(course_key)
        user_id = event_data.user.id
        username = event_data.user.pii.username
        email = event_data.user.pii.email
        full_name = event_data.user.pii.name
    except AttributeError:
        logger.exception(
            "Unexpected COURSE_PASSING_STATUS_UPDATED payload shape: %r", event_data
        )
        return

    logger.info(
        "COURSE_PASSING_STATUS_UPDATED received: user_id=%s username=%s course_id=%s is_passing=%s",
        user_id,
        username,
        course_key,
        is_passing,
    )

    if not is_passing:
        logger.debug(
            "Ignoring non-passing status update: user_id=%s course_id=%s", user_id, course_key
        )
        return

    config = CertifyMeConfiguration.current()
    if not config.enabled:
        logger.debug(
            "CertifyMe plugin disabled; not issuing for user_id=%s course_id=%s", user_id, course_key
        )
        return
    if not config.auto_issue_certificates:
        logger.debug(
            "Auto-issue-certificates disabled; not issuing for user_id=%s course_id=%s",
            user_id,
            course_key,
        )
        return

    # Local import: keeps Celery/task-registration concerns out of the
    # signal-handler import path, which is exercised on every grade change.
    from openedx_certifyme.tasks import issue_certificate_task

    issue_certificate_task.delay(
        user_id=user_id,
        course_id_str=str(course_key),
        recipient_email=email,
        recipient_name=full_name or username,
        course_name=course_name,
    )
    logger.info("Queued issue_certificate_task for user_id=%s course_id=%s", user_id, course_key)
