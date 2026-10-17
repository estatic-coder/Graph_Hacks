ALERTS = {}
EVENTS = []
PENDING = []

def save(alert):
    ALERTS[alert.alert_id] = alert
    return alert

def load(alert_id):
    return ALERTS[alert_id]

def emit(alert_id, event):
    EVENTS.append((alert_id, event))

def enqueue(alert_id):
    PENDING.append(alert_id)
