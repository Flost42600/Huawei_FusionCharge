"""Interpretation of the charger status code and of its connection status.

The working-status codes (signal 10004 in the cloud) follow the connector
status register 31006 documented by the huawei-solar library (Modbus). A
SmartCharger-7KS-S0 reported "2" with the schedule on and no charge running,
which matches SCHEDULED_WAITING.
"""

from __future__ import annotations

from typing import Any

from .api import ChargerState, Signal
from .const import CHARGING_POWER_THRESHOLD, SIG_CONNECTION, SIG_POWER, SIG_STATUS

STATUS_CODES: dict[int, str] = {
    0: "standby",
    1: "plugged",
    2: "scheduled_waiting",
    3: "charging",
    4: "charging_ended",
    5: "fault",
    6: "orderly_waiting",
    7: "upgrading",
    8: "charging_starting",
    9: "alarm",
    10: "green_waiting",
    11: "green_charging",
}
STATUS_OPTIONS = list(STATUS_CODES.values())

CHARGING_CODES = {3, 11}
PLUGGED_CODES = {1, 2, 3, 4, 6, 8, 10, 11}
UNKNOWN_PLUG_CODES = {5, 7, 9}  # fault, upgrade, alarm: plug state not implied

_STATUS_KEYS = ("status", "devStatus", "connectStatus", "linkStatus", "runningStatus")


def status_code(state: ChargerState | None) -> int | None:
    signal = state.connector.get(SIG_STATUS) if state else None
    if signal is None:
        return None
    for raw in (signal.value, signal.real):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            continue
    return None


def status_key(state: ChargerState | None) -> str | None:
    code = status_code(state)
    return STATUS_CODES.get(code) if code is not None else None


def power_kw(state: ChargerState | None) -> float | None:
    signal = state.connector.get(SIG_POWER) if state else None
    if signal is None:
        return None
    if signal.real is not None:
        return signal.real
    try:
        return float(signal.value)
    except (TypeError, ValueError):
        return None


def is_charging(state: ChargerState | None) -> bool | None:
    """True when power flows, or the status code says charging."""
    power = power_kw(state)
    code = status_code(state)
    if power is None and code is None:
        return None
    return (power is not None and power > CHARGING_POWER_THRESHOLD) or code in CHARGING_CODES


def is_plugged(state: ChargerState | None) -> bool | None:
    code = status_code(state)
    if code is None or code in UNKNOWN_PLUG_CODES or code not in STATUS_CODES:
        return None
    return code in PLUGGED_CODES


def _interpret(value: Any) -> bool | None:
    """Text first ("Disconnected" contains "connect"), then a numeric code."""
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return None
    if any(w in text for w in ("disconnect", "offline", "déconnect", "deconnect", "hors ligne", "abnormal", "anormal")):
        return False
    if any(w in text for w in ("connect", "online", "en ligne", "normal")):
        return True
    try:
        number = int(float(text))
    except ValueError:
        return None
    if number == 1:
        return True
    if number in (0, 2):
        return False
    return None


def charger_online(state: ChargerState | None) -> tuple[bool | None, dict[str, Any]]:
    """(online, raw values used): signal 19999 when the charger has it, else the device tree."""
    if state is None:
        return None, {}
    signal: Signal | None = state.connector.get(SIG_CONNECTION)
    if signal is not None:
        result = _interpret(signal.value)
        if result is None and signal.real is not None:
            result = _interpret(signal.real)
        return result, {"source": "signal_19999", "raw": signal.value}
    meta = state.device_meta or {}
    for key in _STATUS_KEYS:
        if key in meta:
            return _interpret(meta[key]), {"source": f"tree.{key}", "raw": meta[key]}
    return None, {"source": None, "device_meta": meta or None}
