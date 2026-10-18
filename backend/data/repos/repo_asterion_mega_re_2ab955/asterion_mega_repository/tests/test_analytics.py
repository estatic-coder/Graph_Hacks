from services.analytics.models import ServiceProcessor
from services.analytics import validators

def test_analytics_processor():
    assert ServiceProcessor().process(2) == 3

def test_analytics_validator_symbol():
    assert callable(validators.validators_operation_0)
