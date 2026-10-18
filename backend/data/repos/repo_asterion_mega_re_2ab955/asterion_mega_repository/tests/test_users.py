from services.users.models import ServiceProcessor
from services.users import validators

def test_users_processor():
    assert ServiceProcessor().process(2) == 3

def test_users_validator_symbol():
    assert callable(validators.validators_operation_0)
