from .config import MAX_SEND_RETRIES
from .notifier import send,notify
from .budget import release,consume
from .store import save,emit
def dispatch(i):
 while i.attempts<=MAX_SEND_RETRIES:
  i.attempts+=1
  try: i.ticket=send(i.incident_id)
  except TimeoutError:
   emit(i.incident_id,"send_timeout")
   continue
  consume(i)
  i.status="sent"
  emit(i.incident_id,"sent")
  notify(i.incident_id,"sent")
  return save(i)
 release(i)
 i.status="failed"
 emit(i.incident_id,"failed")
 notify(i.incident_id,"failed")
 return save(i)
