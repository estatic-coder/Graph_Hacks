from .config import DEPENDENCIES
def downstream(service):
    found=set();frontier=[service]
    while frontier:
        current=frontier.pop()
        for candidate,needs in DEPENDENCIES.items():
            if current in needs and candidate not in found:
                found.add(candidate);frontier.append(candidate)
    return sorted(found)
