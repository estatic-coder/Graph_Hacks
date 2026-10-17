from aegisops.config import AUTO_ISOLATE, TRUSTED_HOSTS
from aegisops.firewall import isolate_host
from aegisops.audit import record_audit

def execute_response(host: str, priority: str) -> str:
    if priority != "critical":
        return "manual_review"
    if host in TRUSTED_HOSTS or not AUTO_ISOLATE:
        return "awaiting_approval"
    if isolate_host(host):
        record_audit("isolated", host)
        return "isolated"
    return "failed"
