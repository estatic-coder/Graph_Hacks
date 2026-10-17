from .store import load,save,emit,enqueue
from .capacity import acquire
def approve(k):
    r=load(k)
    if r.status!='review': raise ValueError('not in review')
    if not acquire(r):
        r.status='no_slot';emit(k,'approval_slot_denied');return save(r)
    r.status='ready';enqueue(k);emit(k,'approved');return save(r)
def deny(k):
    r=load(k)
    if r.status!='review': raise ValueError('not in review')
    r.status='denied';emit(k,'denied');return save(r)
