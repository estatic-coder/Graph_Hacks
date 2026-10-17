from aegisops.models import Event

def normalize_event(raw: dict) -> Event:
    return Event(host=raw["host"], kind=raw["kind"], severity=int(raw["severity"]), source=raw.get("source", "sensor"))
