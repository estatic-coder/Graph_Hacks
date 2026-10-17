from .store import load,save,emit,enqueue
from .budget import reserve
def approve(k):
 i=load(k)
 if i.status!="review": raise ValueError("not awaiting review")
 if not reserve(i):
  i.status="no_budget"
  emit(k,"review_budget_denied")
  return save(i)
 i.status="queued"
 enqueue(k)
 emit(k,"approved")
 return save(i)
def reject(k):
 i=load(k)
 if i.status!="review": raise ValueError("not awaiting review")
 i.status="rejected"
 emit(k,"rejected")
 return save(i)
