from services.subscriptions.models import ServiceProcessor
from services.subscriptions import validators

def test_subscriptions_processor():
    assert ServiceProcessor().process(2) == 3

def test_subscriptions_validator_symbol():
    assert callable(validators.validators_operation_0)
