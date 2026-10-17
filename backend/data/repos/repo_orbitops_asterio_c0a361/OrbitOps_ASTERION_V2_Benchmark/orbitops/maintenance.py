from .credits import HELD, release
from .store import ALERTS, emit

def sweep_holds():
    cleaned = []
    for alert_id in list(HELD):
        alert = ALERTS.get(alert_id)
        if alert is not None and alert.status in {"failed", "sent", "declined"}:
            release(alert)
            emit(alert_id, "orphan_released")
            cleaned.append(alert_id)
    return cleaned
