from dataclasses import dataclass
@dataclass
class Rollout:
    rollout_id: str
    service: str
    environment: str
    version: str
    status: str = 'new'
    attempts: int = 0
    reserved: bool = False
    artifact: str | None = None
