MESSAGES = []

def send_notice(payment_id, status):
    MESSAGES.append((payment_id, status))
