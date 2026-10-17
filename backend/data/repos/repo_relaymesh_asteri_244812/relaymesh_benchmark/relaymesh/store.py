JOBS = {}
EVENTS = []
OUTBOX = []

def save(job):
    JOBS[job.job_id] = job
    return job

def load(job_id):
    return JOBS[job_id]

def emit(job_id, kind):
    EVENTS.append((job_id, kind))

def enqueue(job_id):
    OUTBOX.append(job_id)
