from .config import BLOCKED_TENANTS, VIP_TENANTS

def classify(tenant, payload):
    if tenant in BLOCKED_TENANTS:
        return "blocked"
    if tenant in VIP_TENANTS or payload.startswith("manual:"):
        return "review"
    return "ready"
