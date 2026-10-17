FAIL_ALWAYS = set()
FAIL_ONCE = set()
CALL_COUNTS = {}
AUTHORIZATIONS = []

def authorize(payment_id):
    count = CALL_COUNTS.get(payment_id, 0) + 1
    CALL_COUNTS[payment_id] = count
    if payment_id in FAIL_ALWAYS or (payment_id in FAIL_ONCE and count == 1):
        raise TimeoutError("gateway timed out")
    auth = f"auth:{payment_id}:{count}"
    AUTHORIZATIONS.append(auth)
    return auth
