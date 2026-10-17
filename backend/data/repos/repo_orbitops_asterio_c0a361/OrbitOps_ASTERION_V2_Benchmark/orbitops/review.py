from .store import load, save, emit, enqueue
from .credits import hold

def authorize(alert_id):
    alert = load(alert_id)
    if alert.status != "review":
        raise ValueError("not under review")
    if not hold(alert):
        alert.status = "no_credit"
        emit(alert_id, "approval_credit_denied")
        return save(alert)
    alert.status = "pending"
    enqueue(alert_id)
    emit(alert_id, "authorized")
    return save(alert)

def decline(alert_id):
    alert = load(alert_id)
    if alert.status != "review":
        raise ValueError("not under review")
    alert.status = "declined"
    emit(alert_id, "declined")
    return save(alert)
