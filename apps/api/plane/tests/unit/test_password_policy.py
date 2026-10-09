import time

import pytest

from plane.utils.password_policy import password_policy_errors, password_score


@pytest.mark.unit
@pytest.mark.parametrize(
    "password", ["Testpassword123@", "Zebra#Lamp9Quilt", "Velvet-Otter-42", "Mx7#qLp2vR", "ÀÉÎ12345!"]
)
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
    assert result["feedback"]["suggestions"]


@pytest.mark.unit
def test_composition_failure_caps_a_strong_zxcvbn_score():
    result = password_score("correct horse battery staple")
    assert result["score"] < 3
    assert "Use an uppercase letter." in result["feedback"]["suggestions"]


# Same cases as packages/utils/src/auth.test.ts: classes are Unicode categories and length is
# counted in code points on both sides.
@pytest.mark.unit
@pytest.mark.parametrize(
    "password, errors",
    [
        ("Abcdefg1é", ["a symbol"]),
        ("ÀÉÎ12345!", []),
        ("Ab1!😀😀", ["at least 8 characters"]),
        ("Abcdefg1😀", []),
        ("Abcdefg٣!", []),  # Arabic-Indic digit (Nd)
        ("Abcdefg½!", ["a number"]),  # vulgar fraction (No) is not a number
        ("abcdefgⅠ1!", ["an uppercase letter"]),  # Roman numeral (Nl) is not an uppercase letter
        ("Abcdefg1  ", ["a symbol"]),  # whitespace is not a symbol
    ],
)
def test_character_classes_match_the_ui(password, errors):
    assert password_policy_errors(password) == errors


@pytest.mark.unit
def test_long_passwords_are_scored_quickly():
    start = time.monotonic()
    password_score("aB3!" * 2000)
    assert time.monotonic() - start < 2
