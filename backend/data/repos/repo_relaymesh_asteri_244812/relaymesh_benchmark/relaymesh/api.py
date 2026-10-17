from .workflow import submit
from .review import approve, reject
from .consumer import poll_once
from .replay import replay_dead_letter
from .store import load

def create_job(data):
    return submit(data["job_id"], data["tenant"], data["payload"])

def approve_job(job_id):
    return approve(job_id)

def reject_job(job_id):
    return reject(job_id)

def run_worker_once():
    return poll_once()

def replay_job(job_id):
    return replay_dead_letter(job_id)

def get_job(job_id):
    return load(job_id)
