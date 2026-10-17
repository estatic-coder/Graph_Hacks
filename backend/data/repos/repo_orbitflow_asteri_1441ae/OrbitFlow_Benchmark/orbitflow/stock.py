STOCK = {"book": 5, "laptop": 2}
RESERVATIONS = set()

def reserve(order_id, sku):
    if STOCK.get(sku, 0) <= 0:
        return False
    STOCK[sku] -= 1
    RESERVATIONS.add(order_id)
    return True

def release(order_id, sku):
    if order_id in RESERVATIONS:
        RESERVATIONS.remove(order_id)
        STOCK[sku] += 1
