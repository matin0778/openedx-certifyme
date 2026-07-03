import logging

from config_models.admin import ConfigurationModelAdmin
from django.contrib import admin, messages

from openedx_certifyme.api import CertifyMeAPIError, get_api_client
from openedx_certifyme.models import CertifyMeConfiguration

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
            logger.warning("CertifyMe test_connection failed from admin: %s", exc)
            self.message_user(request, f"Connection failed: {exc}", level=messages.ERROR)
        else:
            logger.info("CertifyMe test_connection succeeded from admin.")
            self.message_user(
                request, f"Connection succeeded: {result['response']}", level=messages.SUCCESS
            )

    test_connection.short_description = "Test connection to CertifyMe"
