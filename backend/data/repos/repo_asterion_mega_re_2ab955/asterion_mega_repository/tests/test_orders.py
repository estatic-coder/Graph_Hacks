from services.orders.models import ServiceProcessor
from services.orders import validators

def test_orders_processor():
    assert ServiceProcessor().process(2) == 3

def test_orders_validator_symbol():
    assert callable(validators.validators_operation_0)
