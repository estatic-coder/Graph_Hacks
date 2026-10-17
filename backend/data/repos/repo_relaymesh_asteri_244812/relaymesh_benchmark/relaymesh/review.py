from .store import load, save, emit, enqueue
from .quota import reserve

def approve(job_id):
    job = load(job_id)
    if job.status != "review":
        raise ValueError("job not under review")
    if not reserve(job):
        job.status = "no_quota"
        emit(job_id, "review_quota_failed")
        return save(job)
    job.status = "queued"
    enqueue(job_id)
    emit(job_id, "review_approved")
    return save(job)

def reject(job_id):
    job = load(job_id)
    if job.status != "review":
        raise ValueError("job not under review")
    job.status = "rejected"
    emit(job_id, "review_rejected")
    return save(job)
