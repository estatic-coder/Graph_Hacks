FAIL_ALWAYS = set()
FAIL_ONCE = set()
CALLS = {}
RECEIPTS = []

def deliver(job_id, payload):
    count = CALLS.get(job_id, 0) + 1
    CALLS[job_id] = count
    if job_id in FAIL_ALWAYS or (job_id in FAIL_ONCE and count == 1):
        raise TimeoutError("transport unavailable")
    receipt = f"receipt:{job_id}:{count}"
    RECEIPTS.append(receipt)
    return receipt
