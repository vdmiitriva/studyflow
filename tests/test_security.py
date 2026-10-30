from studyflow.security import create_csrf_token, verify_csrf_token


def test_valid_csrf_token_is_accepted() -> None:
    session_token = "example-session-token"
    csrf_token = create_csrf_token(session_token)

    assert verify_csrf_token(session_token, csrf_token) is True


def test_invalid_csrf_token_is_rejected() -> None:
    session_token = "example-session-token"

    assert verify_csrf_token(session_token, "wrong-token") is False


def test_csrf_token_from_another_session_is_rejected() -> None:
    session_token = "first-session-token"
    another_session_token = "another-session-token"
    csrf_token = create_csrf_token(session_token)

    assert verify_csrf_token(another_session_token, csrf_token) is False
