from dataclasses import dataclass

@dataclass
class Payment:
    payment_id: str
    account_id: str
    amount: int
    status: str = "new"
    attempts: int = 0
    authorization_id: str | None = None
