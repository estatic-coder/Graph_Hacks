# These boundaries are design contracts, not runtime protection.
ALLOWED_IMPORTS = {
    "orbitops.api": {"orbitops.intake", "orbitops.review", "orbitops.consumer", "orbitops.reopen", "orbitops.store"},
    "orbitops.consumer": {"orbitops.store", "orbitops.worker"},
}
