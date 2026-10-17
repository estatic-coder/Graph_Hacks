from .budget import RESERVED,release
from .store import INCIDENTS,emit
def sweep_reservations():
 result=[]
 for k in list(RESERVED):
  i=INCIDENTS.get(k)
  if i and i.status in {"failed","sent","rejected"}:
   release(i)
   emit(k,"orphan_released")
   result.append(k)
 return result
