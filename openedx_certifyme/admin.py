import logging

from config_models.admin import ConfigurationModelAdmin
from django.contrib import admin, messages

from openedx_certifyme.api import CertifyMeAPIError, get_api_client
from openedx_certifyme.models import CertifyMeCertificate, CertifyMeConfiguration

logger = logging.getLogger(__name__)


@admin.register(CertifyMeConfiguration)
class CertifyMeConfigurationAdmin(ConfigurationModelAdmin):
    """
    Admin for the CertifyMe configuration.

    Built on ``ConfigurationModelAdmin`` (from django-config-models),
    which already gives us: read-only change history, a "revert to
    this configuration" action, and hidden delete. We add a
    "Test connection" action on top, and mask the API key in the
    changelist so it isn't shown in plaintext to anyone with read
    access to the admin list view.
    """

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        return ["masked_api_key" if f == "api_key" else f for f in fields]

    @admin.display(description="API Key")
    def masked_api_key(self, obj):
        if not obj.api_key:
            return "(not set)"
        if len(obj.api_key) <= 4:
            return "****"
        return f"****{obj.api_key[-4:]}"

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions["test_connection"] = (
            CertifyMeConfigurationAdmin.test_connection,
            "test_connection",
            "Test connection to CertifyMe",
        )
        return actions

    def test_connection(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request, "Select exactly one configuration row to test.", level=messages.ERROR
            )
            return

        config = queryset.first()
        if not config.api_url or not config.api_key:
            self.message_user(
                request,
                "Set both API URL and API Key on this row before testing the connection.",
                level=messages.ERROR,
            )
            return

        try:
            client = get_api_client(config=config)
            result = client.test_connection()
        except CertifyMeAPIError as exc:
            logger.warning("Admin user_id=%s CertifyMe test_connection failed: %s", request.user.id, exc)
            self.message_user(request, f"Connection failed: {exc}", level=messages.ERROR)
        else:
            logger.info("Admin user_id=%s CertifyMe test_connection succeeded.", request.user.id)
            self.message_user(
                request, f"Connection succeeded: {result['response']}", level=messages.SUCCESS
            )

    test_connection.short_description = "Test connection to CertifyMe"


@admin.register(CertifyMeCertificate)
class CertifyMeCertificateAdmin(admin.ModelAdmin):
    """
    Read-heavy admin for auditing certificate issuance: every attempt,
    its status, retry count, and the raw CertifyMe response for
    debugging. The one mutating action, "Retry", re-enqueues the same
    Celery task the automatic pipeline and the instructor tools page
    use, so a stuck FAILED row can be nudged without leaving the admin.
    """

    actions = ["retry_selected"]

    list_display = (
        "user",
        "course_id",
        "status",
        "certificate_id",
        "retry_count",
        "issued_at",
        "created",
        "modified",
    )
    list_filter = ("status", "created")
    search_fields = (
        "user__username",
        "user__email",
        "course_id",
        "certificate_id",
    )
    readonly_fields = (
        "user",
        "course_id",
        "certificate_id",
        "verification_url",
        "issued_at",
        "badge_issued_at",
        "badge_response_json",
        "response_json",
        "retry_count",
        "failure_reason",
        "created",
        "modified",
    )
    ordering = ("-created",)

    def has_add_permission(self, request):
        # Certificate records are only ever created by the issuance
        # pipeline (signal -> Celery task), never hand-typed in admin.
        return False

    def retry_selected(self, request, queryset):
        from openedx_certifyme.tasks import issue_certificate_task
        from openedx_certifyme.views._utils import get_course_display_name

        queued = 0
        for certificate in queryset.select_related("user"):
            issue_certificate_task.delay(
                user_id=certificate.user_id,
                course_id_str=str(certificate.course_id),
                recipient_email=certificate.user.email,
                recipient_name=certificate.user.get_full_name() or certificate.user.username,
                course_name=get_course_display_name(certificate.course_id),
            )
            queued += 1

        logger.info("Admin user_id=%s queued retry for %d certificate(s)", request.user.id, queued)
        self.message_user(request, f"Queued {queued} certificate(s) for retry.", level=messages.SUCCESS)

    retry_selected.short_description = "Retry issuance for selected certificates"
