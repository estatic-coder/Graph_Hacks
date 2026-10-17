from .config import REVIEW_TEAMS, MUTED_SOURCES

def decide(alert):
    if alert.source in MUTED_SOURCES:
        return "muted"
    if alert.team in REVIEW_TEAMS or alert.severity >= 8:
        return "review"
    return "ready"
