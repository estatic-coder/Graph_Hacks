TOKENS={"normal":3,"critical":2}
RESERVED=set()
def reserve(i):
 if TOKENS.get(i.team,0)<=0: return False
 TOKENS[i.team]-=1
 RESERVED.add(i.incident_id)
 i.reservation=True
 return True
def release(i):
 if i.incident_id in RESERVED:
  RESERVED.remove(i.incident_id)
  TOKENS[i.team]+=1
 i.reservation=False
def consume(i):
 RESERVED.discard(i.incident_id)
 i.reservation=False
