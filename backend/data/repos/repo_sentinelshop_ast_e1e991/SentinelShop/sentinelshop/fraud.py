from sentinelshop.config import MAX_FRAUD_SCORE

def fraud_score(user_id: str, amount: int) -> int:
    score = 10 if user_id.startswith("trusted") else 35
    if amount > 500:
        score += 40
    return score

def is_high_risk(user_id: str, amount: int) -> bool:
    return fraud_score(user_id, amount) > MAX_FRAUD_SCORE
