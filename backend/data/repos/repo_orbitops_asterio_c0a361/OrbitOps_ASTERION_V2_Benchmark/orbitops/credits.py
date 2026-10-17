BALANCE = {"core": 4, "security": 2}
HELD = set()

def hold(alert):
    if BALANCE.get(alert.team, 0) < 1:
        return False
    BALANCE[alert.team] -= 1
    HELD.add(alert.alert_id)
    alert.reserved = True
    return True

def release(alert):
    if alert.alert_id in HELD:
        HELD.remove(alert.alert_id)
        BALANCE[alert.team] += 1
    alert.reserved = False

def commit(alert):
    HELD.discard(alert.alert_id)
    alert.reserved = False
