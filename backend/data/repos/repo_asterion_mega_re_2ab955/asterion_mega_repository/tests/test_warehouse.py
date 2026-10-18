from services.warehouse.models import ServiceProcessor
from services.warehouse import validators

def test_warehouse_processor():
    assert ServiceProcessor().process(2) == 3

def test_warehouse_validator_symbol():
    assert callable(validators.validators_operation_0)
