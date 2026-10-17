PAYMENTS = {}
EVENTS = []

def save(payment):
    PAYMENTS[payment.payment_id] = payment
    return payment

def record(payment_id, kind):
    EVENTS.append((payment_id, kind))

def load(payment_id):
    return PAYMENTS[payment_id]
