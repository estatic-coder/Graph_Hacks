from services.shipping.models import ServiceProcessor
from services.shipping import validators

def test_shipping_processor():
    assert ServiceProcessor().process(2) == 3

def test_shipping_validator_symbol():
    assert callable(validators.validators_operation_0)
