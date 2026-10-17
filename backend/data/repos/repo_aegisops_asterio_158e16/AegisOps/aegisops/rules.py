from aegisops.config import SEVERITY_THRESHOLD, TRUSTED_HOSTS

def is_suspicious(kind: str) -> bool:
    return kind in {"malware", "credential_attack", "lateral_movement"}

def classify_event(host: str, kind: str, severity: int) -> str:
    if host in TRUSTED_HOSTS:
        return "review"
    if severity >= SEVERITY_THRESHOLD and is_suspicious(kind):
        return "critical"
    if is_suspicious(kind):
        return "warning"
    return "ignore"
