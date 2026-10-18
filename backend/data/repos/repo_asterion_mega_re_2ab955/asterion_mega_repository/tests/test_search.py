from services.search.models import ServiceProcessor
from services.search import validators

def test_search_processor():
    assert ServiceProcessor().process(2) == 3

def test_search_validator_symbol():
    assert callable(validators.validators_operation_0)
