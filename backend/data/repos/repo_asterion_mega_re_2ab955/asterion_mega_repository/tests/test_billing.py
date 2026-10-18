from services.billing.models import ServiceProcessor
from services.billing import validators

def test_billing_processor():
    assert ServiceProcessor().process(2) == 3

def test_billing_validator_symbol():
    assert callable(validators.validators_operation_0)
