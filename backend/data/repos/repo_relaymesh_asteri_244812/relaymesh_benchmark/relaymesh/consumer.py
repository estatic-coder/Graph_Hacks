from .store import OUTBOX, load
from .worker import dispatch

def poll_once():
    if not OUTBOX:
        return None
    job_id = OUTBOX.pop(0)
    job = load(job_id)
    if job.status != "queued":
        return job
    return dispatch(job)
