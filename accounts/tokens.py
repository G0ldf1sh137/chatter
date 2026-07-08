from django.core import signing

SALT = "accounts.email-verification"


class TokenExpired(Exception):
    pass


class TokenInvalid(Exception):
    pass


def generate_verification_token(user):
    return signing.dumps({"user_id": user.pk}, salt=SALT)


def verify_token(token, max_age):
    try:
        data = signing.loads(token, salt=SALT, max_age=max_age)
    except signing.SignatureExpired:
        raise TokenExpired
    except signing.BadSignature:
        raise TokenInvalid
    return data["user_id"]
