from .store import QUEUE,load
from .worker import dispatch
def poll_once():
 if not QUEUE: return None
 k=QUEUE.pop(0)
 i=load(k)
 if i.status!="queued": return i
 return dispatch(i)
