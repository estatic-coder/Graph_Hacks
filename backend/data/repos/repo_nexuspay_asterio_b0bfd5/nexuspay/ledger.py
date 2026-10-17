BALANCES = {"regular-1": 2000, "vip-1": 5000, "blocked-1": 1000}
HOLDS = {}

def place_hold(payment_id, account_id, amount):
    if BALANCES.get(account_id, 0) < amount:
        return False
    BALANCES[account_id] -= amount
    HOLDS[payment_id] = (account_id, amount)
    return True

def release_hold(payment_id):
    hold = HOLDS.pop(payment_id, None)
    if hold is not None:
        account_id, amount = hold
        BALANCES[account_id] += amount

def capture_hold(payment_id):
    return HOLDS.pop(payment_id, None) is not None
