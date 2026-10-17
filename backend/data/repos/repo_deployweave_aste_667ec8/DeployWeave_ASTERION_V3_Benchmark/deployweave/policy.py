from .config import CRITICAL_SERVICES,MUTED_ENVS,DEPENDENCIES
from .registry import VERSIONS
def classify(r):
    if r.environment in MUTED_ENVS: return 'muted'
    if r.service in CRITICAL_SERVICES or r.environment == 'production': return 'review'
    return 'ready'
def dependencies_healthy(r):
    for dependency in DEPENDENCIES.get(r.service, ()):
        if VERSIONS.get(dependency) is None: return False
    return True
