import pytest

from plane.utils.password_policy import password_policy_errors, password_score


@pytest.mark.unit
@pytest.mark.parametrize("password", ["Testpassword123@", "ABCDEFG1!", "Aa1!aaaa"])
def test_accepts_passwords_meeting_policy(password):
    assert password_policy_errors(password) == []
    assert password_score(password)["score"] >= 3


@pytest.mark.unit
@pytest.mark.parametrize(
    "password, missing",
    [
        ("testpassword123@", "an uppercase letter"),
        ("Testpassword@", "a number"),
        ("Testpassword123", "a symbol"),
        ("Tp1@", "at least 8 characters"),
        ("", "at least 8 characters"),
        (None, "at least 8 characters"),
    ],
)
def test_rejects_passwords_missing_a_rule(password, missing):
    assert missing in password_policy_errors(password)
    assert password_score(password)["score"] < 3
