from services.pricing.models import ServiceProcessor
from services.pricing import validators

def test_pricing_processor():
    assert ServiceProcessor().process(2) == 3

def test_pricing_validator_symbol():
    assert callable(validators.validators_operation_0)
