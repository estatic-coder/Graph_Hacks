from .store import READY,load
from .worker import execute
def poll_once():
    if not READY: return None
    k=READY.pop(0)
    r=load(k)
    if r.status!='ready': return r
    return execute(r)
