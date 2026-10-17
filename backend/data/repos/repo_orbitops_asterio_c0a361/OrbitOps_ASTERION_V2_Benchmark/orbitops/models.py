from dataclasses import dataclass
@dataclass
class Alert:
    alert_id: str
    service: str
    team: str
    severity: int
    source: str = "production"
    status: str = "new"
    attempts: int = 0
    reserved: bool = False
    incident_key: str | None = None
