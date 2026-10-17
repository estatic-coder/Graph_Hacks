SLOTS = {'auth': 2, 'ledger': 2, 'gateway': 1}
LOCKED = set()
def acquire(r):
    if SLOTS.get(r.service,0) <= 0: return False
    SLOTS[r.service] -= 1
    LOCKED.add(r.rollout_id)
    r.reserved = True
    return True
def refund(r):
    if r.rollout_id in LOCKED:
        LOCKED.remove(r.rollout_id)
        SLOTS[r.service] += 1
    r.reserved = False
def commit(r):
    LOCKED.discard(r.rollout_id)
    r.reserved = False
