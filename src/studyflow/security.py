import hashlib
import hmac

from pwdlib import PasswordHash

from studyflow.settings import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_csrf_token(session_token: str) -> str:
    return hmac.new(
        settings.csrf_secret.encode("utf-8"),
        session_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    expected_token = create_csrf_token(session_token)

    return hmac.compare_digest(expected_token, csrf_token)
