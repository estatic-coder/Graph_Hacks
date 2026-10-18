from services.fraud.models import ServiceProcessor
from services.fraud import validators

def test_fraud_processor():
    assert ServiceProcessor().process(2) == 3

def test_fraud_validator_symbol():
    assert callable(validators.validators_operation_0)
