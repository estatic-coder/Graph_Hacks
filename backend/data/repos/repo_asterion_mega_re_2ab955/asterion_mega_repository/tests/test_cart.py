from services.cart.models import ServiceProcessor
from services.cart import validators

def test_cart_processor():
    assert ServiceProcessor().process(2) == 3

def test_cart_validator_symbol():
    assert callable(validators.validators_operation_0)
