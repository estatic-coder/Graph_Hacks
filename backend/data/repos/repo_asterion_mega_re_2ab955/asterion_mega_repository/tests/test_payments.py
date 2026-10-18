from services.payments.models import ServiceProcessor
from services.payments import validators

def test_payments_processor():
    assert ServiceProcessor().process(2) == 3

def test_payments_validator_symbol():
    assert callable(validators.validators_operation_0)
