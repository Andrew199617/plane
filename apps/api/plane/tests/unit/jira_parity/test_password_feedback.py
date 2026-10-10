# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Password failures expose stable rule keys and preserve retry state without echoing input."""

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.test import RequestFactory
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIRequestFactory, force_authenticate

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.views.app.password_management import ResetPasswordEndpoint
from plane.authentication.views.common import ChangePasswordEndpoint, SetUserPasswordEndpoint
from plane.authentication.views.space.password_management import ResetPasswordSpaceEndpoint
from plane.license.api.views.admin import InstanceAdminSignUpEndpoint
from plane.license.models import Instance, InstanceAdmin

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def auth_settings(settings):
    settings.WEB_URL = "https://plane.example.test"
    settings.APP_BASE_URL = None
    settings.ADMIN_BASE_URL = None
    settings.SPACE_BASE_URL = None
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@pytest.mark.parametrize("password, expected_rule", [("Password1!", "strength"), ("Abcdefg1\u00e9", "special")])
def test_signup_adapter_reports_failed_rules(password, expected_rule):
    adapter = Adapter(request=None, provider="email")
    adapter.code = password
    with pytest.raises(AuthenticationException) as raised:
        adapter.validate_password("person@example.test")
    payload = raised.value.get_error_dict()
    assert payload["error_message"] == "PASSWORD_TOO_WEAK"
    assert expected_rule in payload["password_rules"].split(",")
    assert password not in str(payload)


@pytest.mark.django_db
@pytest.mark.parametrize("view", [ChangePasswordEndpoint, SetUserPasswordEndpoint])
def test_password_json_endpoints_report_failed_rules_without_changing_password(create_user, view):
    is_set = view is SetUserPasswordEndpoint
    create_user.is_password_autoset = is_set
    create_user.save(update_fields=["is_password_autoset"])
    original_hash = create_user.password
    data = {"password": "Password1!"} if is_set else {"old_password": "test-password", "new_password": "Password1!"}
    request = APIRequestFactory().post("/auth/set-password/" if is_set else "/auth/change-password/", data)
    force_authenticate(request, user=create_user)
    response = view.as_view()(request)
    assert response.status_code == 400
    assert response.data["error_message"] == "PASSWORD_TOO_WEAK"
    assert response.data["password_rules"] == "strength"
    assert "Password1!" not in str(response.data)
    create_user.refresh_from_db()
    assert create_user.password == original_hash
    assert create_user.is_password_autoset == is_set


@pytest.mark.django_db
@pytest.mark.parametrize("view", [ResetPasswordEndpoint, ResetPasswordSpaceEndpoint])
def test_password_reset_reports_failed_rules_and_keeps_valid_retry_token(create_user, view):
    uidb64 = urlsafe_base64_encode(force_bytes(create_user.pk))
    token = PasswordResetTokenGenerator().make_token(create_user)
    request = RequestFactory().post("/auth/reset-password/", {"password": "Password1!"})
    original_hash = create_user.password
    response = view.as_view()(request, uidb64=uidb64, token=token)
    assert response.status_code == 302
    params = parse_qs(urlparse(response.url).query)
    assert params["error_message"] == ["PASSWORD_TOO_WEAK"]
    assert params["password_rules"] == ["strength"]
    assert params["uidb64"] == [uidb64]
    assert params["token"] == [token]
    assert "Password1!" not in response.url
    create_user.refresh_from_db()
    assert create_user.password == original_hash
    assert PasswordResetTokenGenerator().check_token(create_user, token)


@pytest.mark.django_db
def test_instance_admin_signup_rejects_guessable_password_with_feedback():
    Instance.objects.create(
        instance_name="Test Instance",
        instance_id=str(uuid.uuid4()),
        current_version="1.0.0",
        domain="https://plane.example.test",
        last_checked_at=timezone.now(),
        is_setup_done=False,
    )
    request = RequestFactory().post(
        "/api/instances/admins/sign-up/",
        {"email": "setup@example.test", "first_name": "Setup", "password": "Welcome1!"},
    )
    request.user = AnonymousUser()
    response = InstanceAdminSignUpEndpoint.as_view()(request)
    assert response.status_code == 302
    params = parse_qs(urlparse(response.url).query)
    assert params["password_rules"] == ["strength"]
    assert params["error_message"] == ["PASSWORD_TOO_WEAK"]
    assert not InstanceAdmin.objects.exists()
