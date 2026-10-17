from .capacity import LOCKED,refund
from .store import ROLLOUTS,emit
def sweep_locks():
    cleaned=[]
    for k in list(LOCKED):
        r=ROLLOUTS.get(k)
        if r is not None and r.status in {'rolled_back','deployed','denied'}:
            refund(r);emit(k,'orphan_refunded');cleaned.append(k)
    return cleaned
