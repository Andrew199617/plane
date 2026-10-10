# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.utils import timezone
from django.db.models import Q

# Third party imports
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

# Module imports
from plane.db.models import APIToken


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authentication with an API Key
    """

    www_authenticate_realm = "api"
    media_type = "application/json"
    auth_header_name = "X-Api-Key"

    def get_api_token(self, request):
        return request.headers.get(self.auth_header_name)

    def validate_api_token(self, token, request=None):
        try:
            api_token = APIToken.objects.select_related("user", "workspace").get(
                Q(Q(expired_at__gt=timezone.now()) | Q(expired_at__isnull=True)),
                token=token,
                is_active=True,
                user__is_active=True,
            )
        except APIToken.DoesNotExist:
            raise AuthenticationFailed("Given API token is not valid")

        # jira-parity: an agent account's token only works in its own workspace
        if request is not None and not self.agent_token_allowed(api_token, request):
            raise AuthenticationFailed("Given API token is not valid for this workspace")

        # save api token last used
        api_token.last_used = timezone.now()
        api_token.save(update_fields=["last_used"])
        return (api_token.user, api_token.token)

    def authenticate(self, request):
        token = self.get_api_token(request=request)
        if not token:
            return None

        # Validate the API token
        user, token = self.validate_api_token(token, request=request)
        return user, token

    @staticmethod
    def agent_token_allowed(api_token, request):
        """Scope agent and bot tokens, including tokens minted for humans before the account marker
        was introduced. Personal tokens retain their existing instance-wide scope."""
        from plane.utils.agent import AGENT, AGENT_BOT_TYPE
        from plane.db.models import WorkspaceMember

        agent_account = api_token.user.bot_type == AGENT_BOT_TYPE
        if not agent_account and api_token.user_type != 1:
            return True
        if api_token.workspace_id is None:
            # Existing integration bots use instance-wide tokens. Agent accounts and the legacy
            # human tokens minted through /agents/ must always be workspace-bound.
            return api_token.user.is_bot and not agent_account
        if api_token.user_type == 1 and api_token.description == "Agent token" and not agent_account:
            return False
        if (
            agent_account
            and not WorkspaceMember.objects.filter(
                workspace_id=api_token.workspace_id, member_id=api_token.user_id, role=AGENT, is_active=True
            ).exists()
        ):
            return False
        kwargs = (getattr(request, "parser_context", None) or {}).get("kwargs") or {}
        slug = kwargs.get("slug")
        workspace_id = kwargs.get("workspace_id")
        if slug is not None and api_token.workspace.slug != slug:
            return False
        return workspace_id is None or str(api_token.workspace_id) == str(workspace_id)
