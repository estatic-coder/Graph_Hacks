FAILURES = set()
LABELS = []

def create_label(order_id):
    if order_id in FAILURES:
        raise TimeoutError("carrier unavailable")
    LABELS.append(order_id)
    return f"label:{order_id}"
