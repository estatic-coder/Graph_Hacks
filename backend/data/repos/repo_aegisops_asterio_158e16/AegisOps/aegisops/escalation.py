from aegisops.models import Incident
from aegisops.store import save_incident
from aegisops.notifications import notify_security_team, notify_operations
from aegisops.remediation import execute_response
from aegisops.audit import record_audit

def open_incident(host: str, priority: str) -> Incident:
    incident = save_incident(Incident(host=host, priority=priority))
    notify_security_team(host, priority)
    if priority == "critical":
        incident.status = execute_response(host, priority)
        notify_operations(host)
    else:
        incident.status = "manual_review"
    record_audit("incident_created", host)
    return incident
