from .models import Job
from .policy import classify
from .quota import reserve
from .store import save, emit, enqueue

def submit(job_id, tenant, payload):
    job = Job(job_id, tenant, payload)
    decision = classify(tenant, payload)
    if decision == "blocked":
        job.status = "blocked"
        emit(job_id, "blocked")
        return job
    if decision == "review":
        job.status = "review"
        save(job)
        emit(job_id, "review_requested")
        return job
    if not reserve(job):
        job.status = "no_quota"
        emit(job_id, "no_quota")
        return job
    job.status = "queued"
    save(job)
    enqueue(job_id)
    emit(job_id, "queued")
    return job
