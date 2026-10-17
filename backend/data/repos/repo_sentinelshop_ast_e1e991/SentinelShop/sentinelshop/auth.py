def verify_session(session_token: str) -> str:
    if not session_token.startswith("user:"):
        raise PermissionError("invalid session")
    return session_token.split(":", 1)[1]
