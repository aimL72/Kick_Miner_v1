from kickminer.http_client import safe_get


def test_safe_get_dict_path():
    data = {"data": {"user": {"points": 42}}}
    assert safe_get(data, "data", "user", "points") == 42


def test_safe_get_missing_returns_none():
    assert safe_get({"a": 1}, "b", "c") is None
    assert safe_get(None, "a") is None
    assert safe_get(123, "a") is None


def test_safe_get_list_index():
    data = {"items": [{"id": 1}, {"id": 2}]}
    assert safe_get(data, "items", 1, "id") == 2
    assert safe_get(data, "items", 5, "id") is None
    assert safe_get(data, "items", -1, "id") == 2


def test_safe_get_wrong_type_hop():
    assert safe_get({"a": "string"}, "a", "b") is None
