from dataclasses import dataclass

@dataclass
class Order:
    user_id: str
    sku: str
    quantity: int
    amount: int
    status: str = "pending"
