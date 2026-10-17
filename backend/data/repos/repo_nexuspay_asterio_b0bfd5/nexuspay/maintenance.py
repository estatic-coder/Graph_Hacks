from nexuspay.ledger import HOLDS, release_hold
from nexuspay.store import PAYMENTS, record

def cleanup_orphan_holds():
    cleaned = []
    for payment_id in list(HOLDS):
        payment = PAYMENTS.get(payment_id)
        if payment is None or payment.status in {"failed", "rejected", "refunded"}:
            release_hold(payment_id)
            record(payment_id, "orphan_hold_released")
            cleaned.append(payment_id)
    return cleaned
