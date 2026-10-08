# Rule-based password policy (replaces zxcvbn scoring in this fork).
#
# A password is accepted when it has at least PASSWORD_MIN_LENGTH characters,
# an uppercase letter, a digit and a symbol. Returns a zxcvbn-shaped dict so the
# existing `results["score"] < 3` checks keep working unchanged.

PASSWORD_MIN_LENGTH = 8


def password_policy_errors(password):
    password = password or ""
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"at least {PASSWORD_MIN_LENGTH} characters")
    if not any(c.isupper() for c in password):
        errors.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        errors.append("a number")
    if not any(not c.isalnum() and not c.isspace() for c in password):
        errors.append("a symbol")
    return errors


def password_score(password):
    errors = password_policy_errors(password)
    return {"score": 0 if errors else 4, "feedback": {"suggestions": errors}}
