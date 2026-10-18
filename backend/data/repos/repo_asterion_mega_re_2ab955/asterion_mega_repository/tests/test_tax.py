from services.tax.models import ServiceProcessor
from services.tax import validators

def test_tax_processor():
    assert ServiceProcessor().process(2) == 3

def test_tax_validator_symbol():
    assert callable(validators.validators_operation_0)
