from aegisops.pipeline import process_event
from aegisops.store import find_incidents
from aegisops.firewall import restore_host
from aegisops.audit import record_audit

def ingest_alert(payload: dict):
    return process_event(payload)

def list_host_incidents(host: str):
    return find_incidents(host)

def release_host(host: str) -> bool:
    result = restore_host(host)
    if result:
        record_audit("restored", host)
    return result
