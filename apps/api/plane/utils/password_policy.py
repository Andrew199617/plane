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


def password_policy_errors(password):
    password = password if isinstance(password, str) else ""
    categories = [unicodedata.category(c) for c in password]
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if "Lu" not in categories:
        errors.append("an uppercase letter")
    if "Nd" not in categories:
        errors.append("a number")
    if not any(category[0] in "PS" for category in categories):
        errors.append("a symbol")
    return errors


def password_score(password):
    password = password if isinstance(password, str) else ""
    errors = password_policy_errors(password)
    # zxcvbn raises on an empty string
    result = zxcvbn(password[:ZXCVBN_MAX_LENGTH]) if password else {"score": 0, "feedback": {}}
    feedback = result.get("feedback") or {}
    return {
        "score": min(result["score"], 2) if errors else result["score"],
        "feedback": {
            "warning": feedback.get("warning") or "",
            "suggestions": [f"Use {error}." for error in errors] + list(feedback.get("suggestions") or []),
        },
    }
