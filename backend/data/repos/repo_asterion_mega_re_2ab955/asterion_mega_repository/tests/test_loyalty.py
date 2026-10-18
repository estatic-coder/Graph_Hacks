from services.loyalty.models import ServiceProcessor
from services.loyalty import validators

def test_loyalty_processor():
    assert ServiceProcessor().process(2) == 3

def test_loyalty_validator_symbol():
    assert callable(validators.validators_operation_0)
