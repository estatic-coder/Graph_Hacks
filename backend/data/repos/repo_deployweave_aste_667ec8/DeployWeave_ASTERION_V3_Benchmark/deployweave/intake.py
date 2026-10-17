from .models import Rollout
from .policy import classify,dependencies_healthy
from .capacity import acquire
from .store import save,emit,enqueue
def submit(k,service,environment,version):
    r=Rollout(k,service,environment,version)
    choice=classify(r)
    if choice=='muted':
        r.status='muted';emit(k,'muted');return r
    if not dependencies_healthy(r):
        r.status='blocked';emit(k,'missing_dependency');return save(r)
    if choice=='review':
        r.status='review';emit(k,'review_requested');return save(r)
    if not acquire(r):
        r.status='no_slot';emit(k,'slot_denied');return r
    r.status='ready';save(r);enqueue(k);emit(k,'ready');return r
