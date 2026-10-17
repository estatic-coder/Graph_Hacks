from dataclasses import dataclass

@dataclass
class Event:
    host: str
    kind: str
    severity: int
    source: str = "sensor"

@dataclass
class Incident:
    host: str
    priority: str
    status: str = "open"
