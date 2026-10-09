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
            api_token = APIToken.objects.get(
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
        """Jira-parity: workspace-bound tokens of agent accounts are rejected on another workspace's
        URLs (user-level URLs without a workspace slug, e.g. users/me/, stay allowed)."""
        from plane.utils.agent import AGENT_BOT_TYPE

        if api_token.workspace_id is None or api_token.user.bot_type != AGENT_BOT_TYPE:
            return True
        kwargs = (getattr(request, "parser_context", None) or {}).get("kwargs") or {}
        slug = kwargs.get("slug")
        if slug is None:
            return True
        return api_token.workspace.slug == slug
