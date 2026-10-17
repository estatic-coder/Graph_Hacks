from .config import MAX_ROLLBACKS
from .capacity import acquire
from .store import load,save,emit,enqueue
ROLLBACK_COUNTS={}
def retry_rollback(k):
    r=load(k)
    if r.status!='rolled_back': raise ValueError('not rolled back')
    used=ROLLBACK_COUNTS.get(k,0)
    if used>=MAX_ROLLBACKS: raise ValueError('retry budget exhausted')
    ROLLBACK_COUNTS[k]=used+1
    if not acquire(r):
        emit(k,'retry_slot_denied');return r
    r.attempts=0;r.status='ready';enqueue(k);emit(k,'retried');return save(r)
