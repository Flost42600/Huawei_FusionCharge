"""Status code, plug and connection interpretation."""

from custom_components.huawei_fusioncharge.api import ChargerState, Signal
from custom_components.huawei_fusioncharge.status import (
    charger_online,
    is_charging,
    is_plugged,
    status_key,
)


def state(code=None, power=None, connection=None, meta=None) -> ChargerState:
    s = ChargerState()
    if code is not None:
        s.connector[10004] = Signal(str(code), None)  # as returned by a SmartCharger-7KS-S0
    if power is not None:
        s.connector[10013] = Signal(str(power), power)
    if connection is not None:
        s.connector[19999] = connection
    s.device_meta = meta
    return s


def test_status_codes():
    assert status_key(state(2)) == "scheduled_waiting"
    assert status_key(state(11)) == "green_charging"
    assert status_key(state(42)) is None
    assert status_key(state()) is None


def test_charging_from_power_or_code():
    assert is_charging(state(2, 0.0)) is False
    assert is_charging(state(2, 3.5)) is True
    assert is_charging(state(3, 0.0)) is True
    assert is_charging(state()) is None


def test_plugged():
    assert is_plugged(state(0)) is False
    assert is_plugged(state(2)) is True
    assert is_plugged(state(5)) is None


def test_online_from_signal_text():
    assert charger_online(state(connection=Signal("Disconnected", None)))[0] is False
    assert charger_online(state(connection=Signal("Connected", None)))[0] is True


def test_online_from_device_tree():
    assert charger_online(state(meta={"status": "1"}))[0] is True
    assert charger_online(state(meta={"status": "DISCONNECTED"}))[0] is False
    online, attrs = charger_online(state(meta={"name": "x"}))
    assert online is None and attrs["device_meta"] == {"name": "x"}
