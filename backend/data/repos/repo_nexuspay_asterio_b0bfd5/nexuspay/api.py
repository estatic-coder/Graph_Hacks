from nexuspay.workflow import submit
from nexuspay.review import approve, reject
from nexuspay.refunds import refund
from nexuspay.store import load

def create_payment(payload):
    return submit(payload["payment_id"], payload["account_id"], payload["amount"])

def approve_payment(payment_id):
    return approve(payment_id)

def reject_payment(payment_id):
    return reject(payment_id)

def refund_payment(payment_id):
    return refund(payment_id)

def get_payment(payment_id):
    return load(payment_id)
