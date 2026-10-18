from services.checkout.models import ServiceProcessor
from services.checkout import validators

def test_checkout_processor():
    assert ServiceProcessor().process(2) == 3

def test_checkout_validator_symbol():
    assert callable(validators.validators_operation_0)
