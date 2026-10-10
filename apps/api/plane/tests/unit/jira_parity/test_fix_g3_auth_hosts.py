# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Auth redirects may follow the request's allowed origin; emailed/stored links never do."""

import os
import uuid
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from plane.authentication.utils import host as auth_host
from plane.db.models import User
from plane.license.models import Instance
from plane.utils import host as utils_host
from plane.utils.path_validator import get_allowed_hosts, get_safe_redirect_url

WEB = "https://plane.example.test"
ALT = "http://phone.example.test:3300"
ALT_HOST = "phone.example.test:3300"
PASSWORD = "Zebra#Lamp9Quilt"


@pytest.fixture(autouse=True)
def host_settings(settings):
    settings.WEB_URL = WEB
    settings.APP_BASE_URL = None
    settings.ADMIN_BASE_URL = None
    settings.SPACE_BASE_URL = None
    settings.CORS_ALLOWED_ORIGINS = [WEB, ALT]
    settings.ALLOWED_HOSTS = ["*"]
    # keep the auth throttle and cache invalidation off the shared Redis
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    return settings


def _client():
    return Client(HTTP_USER_AGENT="Mozilla/5.0 (pytest)")


def _request(host=ALT_HOST, secure=False):
    return RequestFactory().get("/", HTTP_HOST=host, secure=secure)


@pytest.mark.unit
@pytest.mark.parametrize("base_host", [auth_host.base_host, utils_host.base_host])
class TestBaseHost:
    def test_default_ignores_the_request_origin(self, base_host):
        request = _request()
        assert base_host(request=request) == WEB
        assert base_host(request=request, is_app=True) == WEB
        assert base_host(request=request, is_space=True) == f"{WEB}/spaces/"

    def test_default_uses_app_base_url_for_app_links(self, base_host, settings):
        settings.APP_BASE_URL = "https://app.example.test"
        assert base_host(request=_request(), is_app=True) == "https://app.example.test"

    def test_opt_in_follows_an_allowed_request_origin(self, base_host, settings):
        settings.APP_BASE_URL = "https://app.example.test"
        request = _request()
        assert base_host(request=request, is_app=True, allow_request_origin=True) == ALT
        assert base_host(request=request, is_space=True, allow_request_origin=True) == f"{ALT}/spaces/"

    @pytest.mark.parametrize(
        "host, secure",
        [("evil.example.test", False), (ALT_HOST, True)],  # not allowed / https variant
    )
    def test_opt_in_ignores_origins_that_are_not_allowed(self, base_host, host, secure):
        assert base_host(request=_request(host, secure), is_app=True, allow_request_origin=True) == WEB


@pytest.mark.unit
def test_redirect_host_opts_in():
    assert auth_host.redirect_host(_request(), is_app=True) == ALT
    assert auth_host.redirect_host(_request("evil.example.test"), is_app=True) == WEB


@pytest.mark.unit
class TestSafeRedirectOnAllowedOrigin:
    def test_next_path_is_kept_on_an_allowed_request_origin(self):
        assert get_safe_redirect_url(ALT, "/ws/projects/") == f"{ALT}/?next_path=/ws/projects/"
        assert ALT_HOST in get_allowed_hosts(f"{ALT}/spaces/board")

    @pytest.mark.parametrize("base_url", ["http://evil.example.test", "https://phone.example.test:3300"])
    def test_other_hosts_are_still_rejected(self, base_url):
        assert get_safe_redirect_url(base_url, "/ws/projects/", {"error_code": 1}) == f"{base_url}?error_code=1"
        assert urlparse(base_url).netloc not in get_allowed_hosts(base_url)


@pytest.fixture
def instance(db):
    Instance.objects.update_or_create(
        id=Instance.objects.first().id if Instance.objects.exists() else uuid.uuid4(),
        defaults={
            "instance_name": "Test Instance",
            "instance_id": str(uuid.uuid4()),
            "current_version": "1.0.0",
            "domain": WEB,
            "last_checked_at": timezone.now(),
            "is_setup_done": True,
        },
    )


@pytest.fixture
def human(db):
    user = User.objects.create(email="g3-human@example.test", username=uuid.uuid4().hex, is_active=True)
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.mark.unit
@pytest.mark.django_db
class TestAuthViewsOnAlternateOrigin:
    def test_sign_in_redirects_back_to_the_alternate_origin_with_next_path(self, instance, human):
        response = _client().post(
            reverse("sign-in"),
            {"email": human.email, "password": PASSWORD, "next_path": "/ws/projects/"},
            HTTP_HOST=ALT_HOST,
        )
        assert response.status_code == 302
        assert response.url == f"{ALT}/?next_path=/ws/projects/"

    def test_space_sign_in_redirects_back_to_the_alternate_origin_with_next_path(self, instance, human):
        response = _client().post(
            reverse("space-sign-in"),
            {"email": human.email, "password": PASSWORD, "next_path": "/issues/board"},
            HTTP_HOST=ALT_HOST,
        )
        assert response.status_code == 302
        assert response.url == f"{ALT}/spaces/issues/board"

    @pytest.mark.parametrize("path", ["/auth/forgot-password/", "/auth/spaces/forgot-password/"])
    @patch.dict(os.environ, {"EMAIL_HOST": "smtp.example.test"})
    def test_reset_link_uses_the_configured_origin(self, instance, human, path):
        target = "authentication.views.space" if "spaces" in path else "authentication.views.app"
        with patch(f"plane.{target}.password_management.forgot_password.delay") as send:
            response = _client().post(path, {"email": human.email}, HTTP_HOST=ALT_HOST)
        assert response.status_code == 200
        current_site = send.call_args.args[4]
        assert current_site.startswith(WEB)
        assert ALT_HOST not in current_site
