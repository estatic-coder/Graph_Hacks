from .store import PENDING, load
from .worker import deliver

def drain_one():
    if not PENDING:
        return None
    alert_id = PENDING.pop(0)
    alert = load(alert_id)
    if alert.status != "pending":
        return alert
    return deliver(alert)
