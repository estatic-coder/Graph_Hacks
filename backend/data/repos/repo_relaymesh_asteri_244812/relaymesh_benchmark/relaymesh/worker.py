from .config import MAX_DELIVERY_RETRIES
from .transport import deliver
from .quota import release, consume
from .store import save, emit
from .notify import notify

def dispatch(job):
    while job.attempts <= MAX_DELIVERY_RETRIES:
        job.attempts += 1
        try:
            job.receipt = deliver(job.job_id, job.payload)
        except TimeoutError:
            emit(job.job_id, "delivery_timeout")
            continue
        consume(job)
        job.status = "delivered"
        emit(job.job_id, "delivered")
        notify(job.job_id, "delivered")
        return save(job)
    release(job)
    job.status = "dead_letter"
    emit(job.job_id, "dead_letter")
    notify(job.job_id, "dead_letter")
    return save(job)
