from services.support.models import ServiceProcessor
from services.support import validators

def test_support_processor():
    assert ServiceProcessor().process(2) == 3

def test_support_validator_symbol():
    assert callable(validators.validators_operation_0)
