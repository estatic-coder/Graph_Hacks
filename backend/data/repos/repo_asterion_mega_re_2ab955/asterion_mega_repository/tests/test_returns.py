from services.returns.models import ServiceProcessor
from services.returns import validators

def test_returns_processor():
    assert ServiceProcessor().process(2) == 3

def test_returns_validator_symbol():
    assert callable(validators.validators_operation_0)
