def charge_card(user_id: str, amount: int) -> str:
    if amount <= 0:
        raise ValueError("amount must be positive")
    return f"charge:{user_id}:{amount}"
