MESSAGES: list[str] = []

def notify_security_team(host: str, priority: str) -> None:
    MESSAGES.append(f"security:{host}:{priority}")

def notify_operations(host: str) -> None:
    MESSAGES.append(f"operations:{host}")
