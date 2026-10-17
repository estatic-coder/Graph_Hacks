from .quota import RESERVED, release
from .store import JOBS, emit

def sweep_orphans():
    for job_id in list(RESERVED):
        job = JOBS.get(job_id)
        if job is None:
            continue
        if job.status in {"dead_letter", "rejected", "delivered"}:
            release(job)
            emit(job_id, "orphan_released")
