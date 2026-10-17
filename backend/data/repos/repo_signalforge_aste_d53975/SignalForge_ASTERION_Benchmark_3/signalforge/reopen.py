from .config import MAX_REOPEN
from .store import load,save,emit,enqueue
from .budget import reserve
REOPEN_COUNTS={}
def reopen_failed(k):
 i=load(k)
 if i.status!="failed": raise ValueError("not failed")
 n=REOPEN_COUNTS.get(k,0)
 if n>=MAX_REOPEN: raise ValueError("reopen limit reached")
 REOPEN_COUNTS[k]=n+1
 if not reserve(i):
  emit(k,"reopen_budget_denied")
  return i
 i.attempts=0
 i.status="queued"
 enqueue(k)
 emit(k,"reopened")
 return save(i)
