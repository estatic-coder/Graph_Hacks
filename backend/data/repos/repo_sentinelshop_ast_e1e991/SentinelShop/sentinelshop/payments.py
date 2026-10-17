from sentinelshop.config import MIN_PAYMENT_AMOUNT
from sentinelshop.fraud import is_high_risk
from sentinelshop.gateway import charge_card

def authorize_payment(user_id: str, amount: int) -> str | None:
    if amount < MIN_PAYMENT_AMOUNT:
        return None
    if is_high_risk(user_id, amount):
        return None
    return charge_card(user_id, amount)
