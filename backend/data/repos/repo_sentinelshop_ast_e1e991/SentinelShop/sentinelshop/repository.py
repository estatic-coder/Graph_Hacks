from sentinelshop.models import Order

ORDERS: list[Order] = []

def save_order(order: Order) -> Order:
    ORDERS.append(order)
    return order

def get_orders_for_user(user_id: str) -> list[Order]:
    return [order for order in ORDERS if order.user_id == user_id]
