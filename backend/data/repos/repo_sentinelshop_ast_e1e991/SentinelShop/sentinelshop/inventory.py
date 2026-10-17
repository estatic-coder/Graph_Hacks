from sentinelshop.config import DEFAULT_STOCK

STOCK = dict(DEFAULT_STOCK)

def check_stock(sku: str, quantity: int) -> bool:
    return quantity > 0 and STOCK.get(sku, 0) >= quantity

def reserve_stock(sku: str, quantity: int) -> bool:
    if not check_stock(sku, quantity):
        return False
    STOCK[sku] -= quantity
    return True

def restore_stock(sku: str, quantity: int) -> None:
    STOCK[sku] = STOCK.get(sku, 0) + quantity
