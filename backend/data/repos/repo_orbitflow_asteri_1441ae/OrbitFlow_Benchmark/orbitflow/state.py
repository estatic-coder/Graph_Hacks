from dataclasses import dataclass

@dataclass
class Shipment:
    order_id: str
    customer_id: str
    amount: int
    status: str = "new"
    attempts: int = 0
