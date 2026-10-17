MAX_HEALTH_RETRIES = 2
MAX_ROLLBACKS = 1
CRITICAL_SERVICES = {'gateway'}
MUTED_ENVS = {'sandbox'}
DEPENDENCIES = {'gateway': ('auth', 'ledger'), 'auth': ('ledger',), 'ledger': ()}
