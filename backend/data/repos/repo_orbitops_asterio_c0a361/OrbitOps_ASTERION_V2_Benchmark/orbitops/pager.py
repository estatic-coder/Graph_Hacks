ALWAYS_FAIL = set()
FAIL_FIRST = set()
CALLS = {}
INCIDENTS = []
NOTICES = []

def send_page(alert_id):
    n = CALLS.get(alert_id, 0) + 1
    CALLS[alert_id] = n
    if alert_id in ALWAYS_FAIL or (alert_id in FAIL_FIRST and n == 1):
        raise TimeoutError("pager unavailable")
    key = f"INC-{alert_id}-{n}"
    INCIDENTS.append(key)
    return key

def notify(alert_id, kind):
    NOTICES.append((alert_id, kind))
