# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
from django.http import HttpRequest

# Third party imports
from rest_framework.request import Request

# Module imports
from plane.utils.ip_address import get_client_ip


def base_host(
    request: Request | HttpRequest,
    is_admin: bool = False,
    is_space: bool = False,
    is_app: bool = False,
    allow_request_origin: bool = False,
) -> str:
    """Utility function to return host / origin from the request"""
    # Calculate the base origin from request
    base_origin = settings.WEB_URL or settings.APP_BASE_URL

    # jira-parity: with allow_request_origin (interactive auth redirects only, never emailed or
    # stored links) go back to the request's own origin when it is an allowed origin
    # (e.g. localhost on the desktop vs. a LAN or VPN host name on a phone).
    origin_allowed = False
    if allow_request_origin:
        request_origin = f"{request.scheme}://{request.get_host()}"
        origin_allowed = request_origin in getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if origin_allowed:
            base_origin = request_origin

    # Admin redirection
    if is_admin:
        admin_base_path = getattr(settings, "ADMIN_BASE_PATH", None)
        if not isinstance(admin_base_path, str):
            admin_base_path = "/god-mode/"
        if not admin_base_path.startswith("/"):
            admin_base_path = "/" + admin_base_path
        if not admin_base_path.endswith("/"):
            admin_base_path += "/"

        if settings.ADMIN_BASE_URL:
            return settings.ADMIN_BASE_URL + admin_base_path
        else:
            return base_origin + admin_base_path

    # Space redirection
    if is_space:
        space_base_path = getattr(settings, "SPACE_BASE_PATH", None)
        if not isinstance(space_base_path, str):
            space_base_path = "/spaces/"
        if not space_base_path.startswith("/"):
            space_base_path = "/" + space_base_path
        if not space_base_path.endswith("/"):
            space_base_path += "/"

        if settings.SPACE_BASE_URL:
            return settings.SPACE_BASE_URL + space_base_path
        else:
            return base_origin + space_base_path

    # App Redirection
    if is_app:
        if settings.APP_BASE_URL and not origin_allowed:
            return settings.APP_BASE_URL
        else:
            return base_origin

    return base_origin


def redirect_host(request: Request | HttpRequest, **kwargs) -> str:
    """jira-parity: base_host() for interactive auth redirect responses (may follow the request's
    allowed origin). Emailed or stored links (reset, invite, activation) must use base_host()."""
    return base_host(request, allow_request_origin=True, **kwargs)


def user_ip(request: Request | HttpRequest) -> str:
    return get_client_ip(request=request)
