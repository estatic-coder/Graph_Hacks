from .config import MAX_ATTEMPTS
from .pager import send_page, notify
from .credits import commit, release
from .store import emit, save

def deliver(alert):
    while alert.attempts <= MAX_ATTEMPTS:
        alert.attempts += 1
        try:
            alert.incident_key = send_page(alert.alert_id)
        except TimeoutError:
            emit(alert.alert_id, "page_timeout")
            continue
        commit(alert)
        alert.status = "sent"
        emit(alert.alert_id, "sent")
        notify(alert.alert_id, "sent")
        return save(alert)
    release(alert)
    alert.status = "failed"
    emit(alert.alert_id, "failed")
    notify(alert.alert_id, "failed")
    return save(alert)
