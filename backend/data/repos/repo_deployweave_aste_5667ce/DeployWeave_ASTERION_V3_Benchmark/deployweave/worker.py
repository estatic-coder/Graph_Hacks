from .config import MAX_HEALTH_RETRIES
from .registry import install,restore
from .health import probe
from .capacity import commit,refund
from .store import save,emit,audit
from .notifications import notify
def execute(r):
    old=install(r)
    audit(r.rollout_id,'installed')
    while r.attempts <= MAX_HEALTH_RETRIES:
        r.attempts += 1
        if probe(r.rollout_id):
            commit(r)
            r.status='deployed'
            emit(r.rollout_id,'deployed')
            notify(r.rollout_id,'deployed')
            return save(r)
        emit(r.rollout_id,'health_failed')
    restore(r,old)
    audit(r.rollout_id,'restored')
    refund(r)
    r.status='rolled_back'
    emit(r.rollout_id,'rolled_back')
    notify(r.rollout_id,'rolled_back')
    return save(r)
