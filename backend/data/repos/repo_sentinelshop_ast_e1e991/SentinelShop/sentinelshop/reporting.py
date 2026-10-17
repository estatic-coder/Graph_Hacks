from sentinelshop.repository import get_orders_for_user

def total_confirmed_spend(user_id: str) -> int:
    return sum(o.amount for o in get_orders_for_user(user_id) if o.status == "confirmed")
