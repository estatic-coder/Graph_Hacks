FAIL_ALWAYS=set()
FAIL_ONCE=set()
CALLS={}
TICKETS=[]
NOTICES=[]
def send(k):
 n=CALLS.get(k,0)+1
 CALLS[k]=n
 if k in FAIL_ALWAYS or (k in FAIL_ONCE and n==1): raise TimeoutError("unavailable")
 t=f"ticket:{k}:{n}"
 TICKETS.append(t)
 return t
def notify(k,e): NOTICES.append((k,e))
