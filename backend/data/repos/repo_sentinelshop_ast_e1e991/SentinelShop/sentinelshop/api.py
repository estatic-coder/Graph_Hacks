from sentinelshop.auth import verify_session
from sentinelshop.orders import place_order
from sentinelshop.repository import get_orders_for_user

def checkout(session_token: str, sku: str, quantity: int, amount: int):
    user_id = verify_session(session_token)
    return place_order(user_id, sku, quantity, amount)

def order_history(session_token: str):
    user_id = verify_session(session_token)
    return get_orders_for_user(user_id)
