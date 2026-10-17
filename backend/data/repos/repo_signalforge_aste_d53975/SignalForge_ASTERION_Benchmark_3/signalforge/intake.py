from .models import Incident
from .policy import route
from .budget import reserve
from .store import save,emit,enqueue
def open_incident(k,service,team,severity):
 i=Incident(k,service,team,severity)
 decision=route(i)
 if decision=="muted":
  i.status="muted"
  emit(k,"muted")
  return i
 if decision=="review":
  i.status="review"
  emit(k,"review_requested")
  return save(i)
 if not reserve(i):
  i.status="no_budget"
  emit(k,"budget_denied")
  return i
 i.status="queued"
 save(i)
 enqueue(k)
 emit(k,"queued")
 return i
