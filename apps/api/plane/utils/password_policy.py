# Password policy: composition rules plus upstream's zxcvbn score >= 3.
#
# A password is accepted when it has at least PASSWORD_MIN_LENGTH characters, an uppercase letter,
# a number and a symbol, and zxcvbn scores it 3 or more. Returns a zxcvbn-shaped dict so the
# existing `results["score"] < 3` checks keep working unchanged.
#
# Character classes are Unicode general categories, matching getPasswordCriteria() in
# packages/utils/src/auth.ts: length = code points, uppercase = Lu, number = Nd, symbol = P* or S*.

import unicodedata

from zxcvbn import zxcvbn

PASSWORD_MIN_LENGTH = 8
# zxcvbn's run time grows super-linearly with the input length; only score a bounded prefix.
ZXCVBN_MAX_LENGTH = 100


PASSWORD_RULE_DESCRIPTIONS = {
    "length": f"at least {PASSWORD_MIN_LENGTH} characters",
    "uppercase": "an uppercase letter",
    "number": "a number",
    "special": "a symbol",
}


def _failed_composition_rules(password):
    password = password if isinstance(password, str) else ""
    categories = [unicodedata.category(c) for c in password]
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append("length")
    if "Lu" not in categories:
        errors.append("uppercase")
    if "Nd" not in categories:
        errors.append("number")
    if not any(category[0] in "PS" for category in categories):
        errors.append("special")
    return errors


def password_policy_errors(password):
    return [PASSWORD_RULE_DESCRIPTIONS[rule] for rule in _failed_composition_rules(password)]


def password_error_payload(results):
    """Stable rule keys for JSON errors and form redirects; never include password input."""
    return {"password_rules": ",".join(results["failed_rules"])}


def password_score(password):
    password = password if isinstance(password, str) else ""
    failed_rules = _failed_composition_rules(password)
    errors = [PASSWORD_RULE_DESCRIPTIONS[rule] for rule in failed_rules]
    # zxcvbn raises on an empty string
    result = zxcvbn(password[:ZXCVBN_MAX_LENGTH]) if password else {"score": 0, "feedback": {}}
    feedback = result.get("feedback") or {}
    if result["score"] < 3:
        failed_rules.append("strength")
    return {
        "score": min(result["score"], 2) if errors else result["score"],
        "failed_rules": failed_rules,
        "feedback": {
            "warning": feedback.get("warning") or "",
            "suggestions": [f"Use {error}." for error in errors] + list(feedback.get("suggestions") or []),
        },
    }
