from .config import MAX_REPLAY_ATTEMPTS
from .store import load, enqueue, emit, save
from .quota import reserve

REPLAY_COUNTS = {}

def replay_dead_letter(job_id):
    job = load(job_id)
    if job.status != "dead_letter":
        raise ValueError("not a dead letter")
    count = REPLAY_COUNTS.get(job_id, 0)
    if count >= MAX_REPLAY_ATTEMPTS:
        raise ValueError("replay limit reached")
    REPLAY_COUNTS[job_id] = count + 1
    if not reserve(job):
        emit(job_id, "replay_quota_failed")
        return job
    job.attempts = 0
    job.status = "queued"
    enqueue(job_id)
    emit(job_id, "replayed")
    return save(job)
