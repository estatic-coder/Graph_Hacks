from dataclasses import dataclass
@dataclass
class Incident:
 incident_id:str
 service:str
 team:str
 severity:int
 status:str="new"
 attempts:int=0
 reservation:bool=False
 ticket:str|None=None
