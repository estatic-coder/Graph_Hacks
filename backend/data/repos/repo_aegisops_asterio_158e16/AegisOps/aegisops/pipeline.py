from aegisops.telemetry import normalize_event
from aegisops.rules import classify_event
from aegisops.escalation import open_incident
from aegisops.audit import record_audit

def process_event(raw: dict):
    event = normalize_event(raw)
    decision = classify_event(event.host, event.kind, event.severity)
    if decision == "ignore":
        record_audit("ignored", event.host)
        return None
    return open_incident(event.host, decision)
