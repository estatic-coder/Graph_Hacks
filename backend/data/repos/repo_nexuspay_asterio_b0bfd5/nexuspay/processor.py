from nexuspay.config import MAX_GATEWAY_RETRIES
from nexuspay.gateway import authorize
from nexuspay.ledger import release_hold, capture_hold
from nexuspay.store import record, save
from nexuspay.notify import send_notice

def process(payment):
    while payment.attempts <= MAX_GATEWAY_RETRIES:
        payment.attempts += 1
        try:
            payment.authorization_id = authorize(payment.payment_id)
        except TimeoutError:
            record(payment.payment_id, "gateway_timeout")
            continue
        capture_hold(payment.payment_id)
        payment.status = "paid"
        record(payment.payment_id, "paid")
        send_notice(payment.payment_id, "paid")
        return save(payment)
    release_hold(payment.payment_id)
    payment.status = "failed"
    record(payment.payment_id, "failed")
    send_notice(payment.payment_id, "failed")
    return save(payment)
