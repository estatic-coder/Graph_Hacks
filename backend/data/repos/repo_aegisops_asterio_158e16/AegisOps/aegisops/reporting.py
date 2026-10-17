from aegisops.store import find_incidents
from aegisops.audit import AUDIT_LOG

def build_host_report(host: str) -> dict:
    incidents = find_incidents(host)
    return {"host": host, "incident_count": len(incidents), "audit_entries": [entry for entry in AUDIT_LOG if entry.endswith(":" + host)]}
