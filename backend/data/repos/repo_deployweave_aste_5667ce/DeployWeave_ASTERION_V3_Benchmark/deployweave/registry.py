VERSIONS = {'auth':'1.0','ledger':'1.0','gateway':'1.0'}
CHANGES = []
def install(r):
    old = VERSIONS[r.service]
    VERSIONS[r.service] = r.version
    CHANGES.append((r.rollout_id,old,r.version))
    return old
def restore(r,old):
    VERSIONS[r.service] = old
    CHANGES.append((r.rollout_id,r.version,old))
