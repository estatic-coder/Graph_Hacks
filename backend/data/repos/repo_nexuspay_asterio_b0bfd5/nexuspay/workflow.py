from nexuspay.models import Payment
from nexuspay.policy import decide
from nexuspay.ledger import place_hold
from nexuspay.processor import process
from nexuspay.store import save, record
from nexuspay.notify import send_notice

def submit(payment_id, account_id, amount):
    payment = Payment(payment_id, account_id, amount)
    decision = decide(account_id, amount)
    if decision == "blocked":
        payment.status = "blocked"
        record(payment_id, "blocked")
        return payment
    if decision == "review":
        payment.status = "review"
        save(payment)
        record(payment_id, "review_requested")
        return payment
    if not place_hold(payment_id, account_id, amount):
        payment.status = "insufficient_funds"
        record(payment_id, "insufficient_funds")
        send_notice(payment_id, "insufficient_funds")
        return payment
    save(payment)
    return process(payment)
