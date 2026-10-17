CREDITS = {"normal": 5, "vip": 5, "banned": 5}
RESERVED = set()

def reserve(job):
    if CREDITS.get(job.tenant, 0) < 1:
        return False
    CREDITS[job.tenant] -= 1
    RESERVED.add(job.job_id)
    job.reservation = True
    return True

def release(job):
    if job.job_id in RESERVED:
        RESERVED.remove(job.job_id)
        CREDITS[job.tenant] += 1
        job.reservation = False

def consume(job):
    RESERVED.discard(job.job_id)
    job.reservation = False
