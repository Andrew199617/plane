import time

import pytest

from plane.utils.password_policy import password_error_payload, password_policy_errors, password_score


@pytest.mark.unit
@pytest.mark.parametrize(
    "password", ["Testpassword123@", "Zebra#Lamp9Quilt", "Velvet-Otter-42", "Mx7#qLp2vR", "\u00c0\u00c9\u00ce12345!"]
)
def test_accepts_passwords_meeting_policy(password):
    assert password_policy_errors(password) == []
    result = password_score(password)
    assert result["score"] >= 3
    assert result["failed_rules"] == []


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
        (12345678, "at least 8 characters"),
    ],
)
def test_rejects_passwords_missing_a_rule(password, missing):
    assert missing in password_policy_errors(password)
    result = password_score(password)
    assert result["score"] < 3
    assert f"Use {missing}." in result["feedback"]["suggestions"]


@pytest.mark.unit
@pytest.mark.parametrize("password", ["Password1!", "Welcome1!", "Qwerty123!", "Aaaaaaa1!"])
def test_rejects_guessable_passwords_that_meet_the_composition_rules(password):
    assert password_policy_errors(password) == []
    result = password_score(password)
    assert result["score"] < 3
    assert result["failed_rules"] == ["strength"]
    assert result["feedback"]["suggestions"]


@pytest.mark.unit
def test_composition_failure_caps_a_strong_zxcvbn_score():
    result = password_score("correct horse battery staple")
    assert result["score"] < 3
    assert result["failed_rules"] == ["uppercase", "number", "special"]
    assert "Use an uppercase letter." in result["feedback"]["suggestions"]


# Same escaped Unicode cases as packages/utils/src/auth.test.ts.
@pytest.mark.unit
@pytest.mark.parametrize(
    "password, errors",
    [
        ("Abcdefg1\u00e9", ["a symbol"]),
        ("\u00c0\u00c9\u00ce12345!", []),
        ("Ab1!\U0001f600\U0001f600", ["at least 8 characters"]),
        ("Abcdefg1\U0001f600", []),
        ("Abcdefg\u0661!", []),  # Arabic-Indic digit (Nd)
        ("Abcdefg\u00bd!", ["a number"]),  # vulgar fraction (No)
        ("abcdefg\u21671!", ["an uppercase letter"]),  # Roman numeral (Nl)
        ("Abcdefg1 \u00a0", ["a symbol"]),  # whitespace
    ],
)
def test_character_classes_match_the_ui(password, errors):
    assert password_policy_errors(password) == errors


@pytest.mark.unit
def test_feedback_payload_contains_only_rule_keys():
    payload = password_error_payload(password_score("Tp1@"))
    assert payload == {"password_rules": "length,strength"}
    assert "Tp1@" not in str(payload)


@pytest.mark.unit
def test_long_passwords_are_scored_quickly():
    start = time.monotonic()
    password_score("aB3!" * 2000)
    assert time.monotonic() - start < 2
