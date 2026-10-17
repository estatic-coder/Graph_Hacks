ROLLOUTS = {}
EVENTS = []
READY = []
AUDIT = []
def save(r):
    ROLLOUTS[r.rollout_id] = r
    return r
def load(k): return ROLLOUTS[k]
def emit(k,kind): EVENTS.append((k,kind))
def enqueue(k): READY.append(k)
def audit(k,kind): AUDIT.append((k,kind))
