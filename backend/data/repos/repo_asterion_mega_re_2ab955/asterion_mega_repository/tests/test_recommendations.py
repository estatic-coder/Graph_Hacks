from services.recommendations.models import ServiceProcessor
from services.recommendations import validators

def test_recommendations_processor():
    assert ServiceProcessor().process(2) == 3

def test_recommendations_validator_symbol():
    assert callable(validators.validators_operation_0)
