from sentinelshop.inventory import check_stock, reserve_stock
from sentinelshop.models import Order
from sentinelshop.notifications import send_order_confirmation
from sentinelshop.payments import authorize_payment
from sentinelshop.repository import save_order

def place_order(user_id: str, sku: str, quantity: int, amount: int) -> Order:
    order = Order(user_id=user_id, sku=sku, quantity=quantity, amount=amount)
    if not check_stock(sku, quantity):
        order.status = "out_of_stock"
        return order
    receipt = authorize_payment(user_id, amount)
    if receipt is None:
        order.status = "payment_declined"
        return order
    if not reserve_stock(sku, quantity):
        order.status = "out_of_stock"
        return order
    order.status = "confirmed"
    save_order(order)
    send_order_confirmation(user_id, sku)
    return order
