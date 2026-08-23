from __future__ import annotations
import pytest
from sdd_scripts.server_control import PortTarget, parse_target

def test_parse_target_accepts_labelled_port() -> None:
    assert parse_target("Frontend:5173") == PortTarget("Frontend", 5173)

@pytest.mark.parametrize("value", ["5173", ":5173", "Back:0", "Back:65536", "Back:abc"])
def test_parse_target_rejects_invalid_values(value: str) -> None:
    with pytest.raises(Exception):
        parse_target(value)
