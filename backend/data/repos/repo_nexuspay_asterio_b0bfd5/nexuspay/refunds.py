from nexuspay.store import load, record, save
from nexuspay.notify import send_notice
REFUNDS = []

def refund(payment_id):
    payment = load(payment_id)
    if payment.status != "paid":
        raise ValueError("only paid payments can be refunded")
    REFUNDS.append(payment_id)
    payment.status = "refunded"
    record(payment_id, "refunded")
    send_notice(payment_id, "refunded")
    return save(payment)
