ALWAYS_BAD = set()
BAD_FIRST = set()
CHECKS = {}
def probe(k):
    n = CHECKS.get(k,0)+1
    CHECKS[k] = n
    return k not in ALWAYS_BAD and not (k in BAD_FIRST and n == 1)
