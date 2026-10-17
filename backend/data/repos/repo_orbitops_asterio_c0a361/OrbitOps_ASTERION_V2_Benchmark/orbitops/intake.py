from .models import Alert
from .policy import decide
from .store import save, emit, enqueue
from .credits import hold

def submit(alert_id, service, team, severity, source="production"):
    alert = Alert(alert_id, service, team, severity, source)
    route = decide(alert)
    if route == "muted":
        alert.status = "muted"
        emit(alert_id, "muted")
        return alert
    if route == "review":
        alert.status = "review"
        emit(alert_id, "review_requested")
        return save(alert)
    if not hold(alert):
        alert.status = "no_credit"
        emit(alert_id, "credit_denied")
        return alert
    alert.status = "pending"
    save(alert)
    enqueue(alert_id)
    emit(alert_id, "pending")
    return alert
