from services.audit.models import ServiceProcessor
from services.audit import validators

def test_audit_processor():
    assert ServiceProcessor().process(2) == 3

def test_audit_validator_symbol():
    assert callable(validators.validators_operation_0)
