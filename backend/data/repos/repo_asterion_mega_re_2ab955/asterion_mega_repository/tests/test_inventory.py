from services.inventory.models import ServiceProcessor
from services.inventory import validators

def test_inventory_processor():
    assert ServiceProcessor().process(2) == 3

def test_inventory_validator_symbol():
    assert callable(validators.validators_operation_0)
