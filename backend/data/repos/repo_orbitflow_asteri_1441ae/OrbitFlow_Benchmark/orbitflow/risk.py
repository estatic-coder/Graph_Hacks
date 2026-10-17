from orbitflow.config import HIGH_VALUE_LIMIT, VIP_CUSTOMERS

def evaluate_risk(customer_id, amount):
    if customer_id in VIP_CUSTOMERS:
        return "manual_review"
    if amount >= HIGH_VALUE_LIMIT:
        return "manual_review"
    return "approved"
