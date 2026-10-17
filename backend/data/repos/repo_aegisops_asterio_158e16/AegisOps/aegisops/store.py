from aegisops.models import Incident
INCIDENTS: list[Incident] = []

def save_incident(incident: Incident) -> Incident:
    INCIDENTS.append(incident)
    return incident

def find_incidents(host: str) -> list[Incident]:
    return [i for i in INCIDENTS if i.host == host]
