from .intake import submit
from .review import authorize, decline
from .consumer import drain_one
from .reopen import reopen_failed
from .store import load

def create_alert(payload):
    return submit(**payload)

def approve_alert(alert_id):
    return authorize(alert_id)

def reject_alert(alert_id):
    return decline(alert_id)

def run_agent_once():
    return drain_one()

def retry_failed_alert(alert_id):
    return reopen_failed(alert_id)

def get_alert(alert_id):
    return load(alert_id)
