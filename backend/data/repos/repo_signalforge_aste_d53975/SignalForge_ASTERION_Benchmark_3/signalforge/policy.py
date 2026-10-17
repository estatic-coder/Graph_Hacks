from .config import VIP_TEAMS,MUTED_SERVICES
def route(i):
 if i.service in MUTED_SERVICES: return "muted"
 if i.team in VIP_TEAMS or i.severity>=8: return "review"
 return "ready"
