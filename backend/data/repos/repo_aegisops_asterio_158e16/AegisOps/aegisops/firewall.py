BLOCKED_HOSTS: set[str] = set()

def isolate_host(host: str) -> bool:
    BLOCKED_HOSTS.add(host)
    return True

def restore_host(host: str) -> bool:
    BLOCKED_HOSTS.discard(host)
    return True
