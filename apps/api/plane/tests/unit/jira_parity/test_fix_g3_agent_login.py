# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Agent accounts (bot_type "AGENT") only use API tokens: every interactive login path rejects them,
and no magic code or password-reset link is ever issued for them."""

import json
import os
import uuid
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.urls import reverse
from django.utils import timezone

from plane.authentication.adapter.base import Adapter, is_non_interactive_account
from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import User
from plane.license.models import Instance, InstanceAdmin

PASSWORD = "Zebra#Lamp9Quilt"
AGENT_EMAIL = "g3-agent@agents.example.test"
HUMAN_EMAIL = "g3-human@example.test"


class FakeRedis:
    """Just enough of redis for MagicCodeProvider, so the tests never touch the shared Redis."""

    def __init__(self):
        self.store = {}

    def exists(self, key):
        return key in self.store

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)

    def ttl(self, key):
        return 600

    def eval(self, script, numkeys, key, ttl):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]


@pytest.fixture(autouse=True)
def auth_settings(settings):
    settings.WEB_URL = "https://plane.example.test"
    settings.APP_BASE_URL = None
    settings.ADMIN_BASE_URL = None
    settings.SPACE_BASE_URL = None
    settings.ALLOWED_HOSTS = ["*"]
    # keep the auth throttle and cache invalidation off the shared Redis
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    with patch.dict(os.environ, {"EMAIL_HOST": "smtp.example.test"}):
        yield settings


@pytest.fixture
def instance(db):
    instance, _ = Instance.objects.update_or_create(
        id=Instance.objects.first().id if Instance.objects.exists() else uuid.uuid4(),
        defaults={
            "instance_name": "Test Instance",
            "instance_id": str(uuid.uuid4()),
            "current_version": "1.0.0",
            "domain": "https://plane.example.test",
            "last_checked_at": timezone.now(),
            "is_setup_done": True,
        },
    )
    return instance


def _user(email, **fields):
    user = User.objects.create(email=email, username=uuid.uuid4().hex, is_active=True, **fields)
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.fixture
def agent(db):
    return _user(AGENT_EMAIL, bot_type="AGENT", is_password_autoset=True)


@pytest.fixture
def human(db):
    return _user(HUMAN_EMAIL)


def _client():
    return Client(HTTP_USER_AGENT="Mozilla/5.0 (pytest)")


def _signed_in(client):
    return "_auth_user_id" in client.session


@pytest.mark.unit
def test_is_non_interactive_account():
    assert is_non_interactive_account(User(email="a@example.test", bot_type="AGENT"))
    assert is_non_interactive_account(User(email="b@example.test", is_bot=True))
    assert not is_non_interactive_account(User(email="c@example.test"))
    assert not is_non_interactive_account(None)


@pytest.mark.unit
@pytest.mark.django_db
class TestAgentInteractiveLogin:
    @pytest.mark.parametrize("url_name", ["sign-in", "space-sign-in"])
    def test_password_sign_in_is_forbidden(self, instance, agent, url_name):
        client = _client()
        response = client.post(reverse(url_name), {"email": AGENT_EMAIL, "password": PASSWORD})
        assert response.status_code == 302
        assert "BOT_USER_LOGIN_FORBIDDEN" in response.url
        assert not _signed_in(client)

    @pytest.mark.parametrize("url_name", ["sign-in", "space-sign-in"])
    def test_human_control_signs_in(self, instance, human, url_name):
        client = _client()
        response = client.post(reverse(url_name), {"email": HUMAN_EMAIL, "password": PASSWORD})
        assert "error_code" not in response.url
        assert _signed_in(client)

    @pytest.mark.parametrize("url_name", ["magic-sign-in", "space-magic-sign-in"])
    def test_magic_sign_in_with_a_valid_code_is_forbidden(self, instance, agent, url_name):
        redis = FakeRedis()
        redis.set(f"magic_{AGENT_EMAIL}", json.dumps({"current_attempt": 0, "email": AGENT_EMAIL, "token": "123456"}))
        client = _client()
        with patch("plane.authentication.provider.credentials.magic_code.redis_instance", return_value=redis):
            response = client.post(reverse(url_name), {"email": AGENT_EMAIL, "code": "123456"})
        assert response.status_code == 302
        assert "BOT_USER_LOGIN_FORBIDDEN" in response.url
        assert not _signed_in(client)

    @pytest.mark.parametrize("provider", ["google", "github", "gitlab", "gitea"])
    def test_oauth_login_is_forbidden(self, agent, provider):
        adapter = Adapter(request=RequestFactory().get("/"), provider=provider)
        adapter.set_user_data({"email": AGENT_EMAIL, "user": {"is_password_autoset": True}})
        with pytest.raises(AuthenticationException) as raised:
            adapter.complete_login_or_signup()
        assert raised.value.error_message == "BOT_USER_LOGIN_FORBIDDEN"

    def test_admin_sign_in_is_forbidden(self, instance, agent):
        InstanceAdmin.objects.create(instance=instance, user=agent)
        response = _client().post("/api/instances/admins/sign-in/", {"email": AGENT_EMAIL, "password": PASSWORD})
        assert response.status_code == 302
        assert "ADMIN_AUTHENTICATION_FAILED" in response.url


@pytest.mark.unit
@pytest.mark.django_db
class TestAgentCodesAndResetLinks:
    @pytest.mark.parametrize("url_name, view", [("magic-generate", "app"), ("space-magic-generate", "space")])
    def test_magic_generate_issues_no_code(self, instance, agent, human, url_name, view):
        redis = FakeRedis()
        with (
            patch("plane.authentication.provider.credentials.magic_code.redis_instance", return_value=redis),
            patch(f"plane.authentication.views.{view}.magic.magic_link.delay") as send,
        ):
            response = _client().post(reverse(url_name), {"email": AGENT_EMAIL}, content_type="application/json")
            assert response.status_code == 200
            assert response.json() == {"key": f"magic_{AGENT_EMAIL}"}
            assert redis.store == {}
            assert not send.called

            # control: a human gets a code with the same response shape
            response = _client().post(reverse(url_name), {"email": HUMAN_EMAIL}, content_type="application/json")
            assert response.json() == {"key": f"magic_{HUMAN_EMAIL}"}
            assert send.called and f"magic_{HUMAN_EMAIL}" in redis.store

    @pytest.mark.parametrize(
        "path, view", [("/auth/forgot-password/", "app"), ("/auth/spaces/forgot-password/", "space")]
    )
    def test_forgot_password_sends_no_reset_link(self, instance, agent, human, path, view):
        with patch(f"plane.authentication.views.{view}.password_management.forgot_password.delay") as send:
            agent_response = _client().post(path, {"email": AGENT_EMAIL}, content_type="application/json")
            assert not send.called
            human_response = _client().post(path, {"email": HUMAN_EMAIL}, content_type="application/json")
            assert send.called
        assert agent_response.status_code == human_response.status_code == 200
        assert agent_response.json() == human_response.json()
