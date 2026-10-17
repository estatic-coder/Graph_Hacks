from .config import MAX_REOPEN
from .store import load, save, emit, enqueue
from .credits import hold
REOPENED = {}

def reopen_failed(alert_id):
    alert = load(alert_id)
    if alert.status != "failed":
        raise ValueError("not failed")
    used = REOPENED.get(alert_id, 0)
    if used >= MAX_REOPEN:
        raise ValueError("reopen budget exceeded")
    REOPENED[alert_id] = used + 1
    if not hold(alert):
        emit(alert_id, "reopen_credit_denied")
        return alert
    alert.attempts = 0
    alert.status = "pending"
    enqueue(alert_id)
    emit(alert_id, "reopened")
    return save(alert)
