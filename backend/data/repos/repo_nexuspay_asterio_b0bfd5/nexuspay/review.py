from nexuspay.store import load, record
from nexuspay.ledger import place_hold
from nexuspay.processor import process

def approve(payment_id):
    payment = load(payment_id)
    if payment.status != "review":
        raise ValueError("payment not under review")
    if not place_hold(payment_id, payment.account_id, payment.amount):
        payment.status = "insufficient_funds"
        record(payment_id, "review_funds_failed")
        return payment
    record(payment_id, "review_approved")
    return process(payment)

def reject(payment_id):
    payment = load(payment_id)
    if payment.status != "review":
        raise ValueError("payment not under review")
    payment.status = "rejected"
    record(payment_id, "review_rejected")
    return payment
