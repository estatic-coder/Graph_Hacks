from orbitflow.storage import EVENTS

def count_events(kind):
    return sum(1 for _, event in EVENTS if event == kind)
