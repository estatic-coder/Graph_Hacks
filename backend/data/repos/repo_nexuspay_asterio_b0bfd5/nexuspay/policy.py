from nexuspay.config import BLOCKED_ACCOUNTS, REVIEW_THRESHOLD, VIP_ACCOUNTS

def decide(account_id, amount):
    if account_id in BLOCKED_ACCOUNTS:
        return "blocked"
    if account_id in VIP_ACCOUNTS or amount >= REVIEW_THRESHOLD:
        return "review"
    return "approved"
