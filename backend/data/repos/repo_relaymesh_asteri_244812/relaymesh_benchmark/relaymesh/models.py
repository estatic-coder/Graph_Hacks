from dataclasses import dataclass

@dataclass
class Job:
    job_id: str
    tenant: str
    payload: str
    status: str = "new"
    attempts: int = 0
    reservation: bool = False
    receipt: str | None = None
