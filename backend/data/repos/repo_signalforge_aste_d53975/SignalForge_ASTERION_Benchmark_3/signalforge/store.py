INCIDENTS={}
EVENTS=[]
QUEUE=[]
def save(i):
 INCIDENTS[i.incident_id]=i
 return i
def load(k): return INCIDENTS[k]
def emit(k,e): EVENTS.append((k,e))
def enqueue(k): QUEUE.append(k)
