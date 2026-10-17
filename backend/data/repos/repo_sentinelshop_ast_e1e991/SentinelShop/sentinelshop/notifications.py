SENT_MESSAGES: list[str] = []

def send_order_confirmation(user_id: str, sku: str) -> None:
    SENT_MESSAGES.append(f"confirmed:{user_id}:{sku}")
