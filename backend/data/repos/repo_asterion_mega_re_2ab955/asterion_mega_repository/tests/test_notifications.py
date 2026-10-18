from services.notifications.models import ServiceProcessor
from services.notifications import validators

def test_notifications_processor():
    assert ServiceProcessor().process(2) == 3

def test_notifications_validator_symbol():
    assert callable(validators.validators_operation_0)
