from services.catalog.models import ServiceProcessor
from services.catalog import validators

def test_catalog_processor():
    assert ServiceProcessor().process(2) == 3

def test_catalog_validator_symbol():
    assert callable(validators.validators_operation_0)
