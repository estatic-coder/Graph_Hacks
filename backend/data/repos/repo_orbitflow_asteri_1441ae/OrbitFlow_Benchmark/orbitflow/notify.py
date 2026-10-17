MESSAGES = []

def notify_customer(order_id, status):
    MESSAGES.append((order_id, status))
