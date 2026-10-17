from utils import format_user_data

def test_format_user_data():
    assert format_user_data((1, "Alice")) == {"id": 1, "name": "Alice"}
    assert format_user_data(None) is None
