AUDIT_LOG: list[str] = []

def record_audit(action: str, host: str) -> None:
    AUDIT_LOG.append(f"{action}:{host}")
