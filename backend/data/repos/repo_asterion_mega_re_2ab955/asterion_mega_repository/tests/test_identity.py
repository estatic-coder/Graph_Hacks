from services.identity.models import ServiceProcessor
from services.identity import validators

def test_identity_processor():
    assert ServiceProcessor().process(2) == 3

def test_identity_validator_symbol():
    assert callable(validators.validators_operation_0)
