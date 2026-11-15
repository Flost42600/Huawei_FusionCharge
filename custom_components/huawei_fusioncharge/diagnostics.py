"""Diagnostics with every credential and identifier redacted."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_CHARGER_DN, SIG_SOFTWARE
from .coordinator import FusionChargeConfigEntry

TO_REDACT = {CONF_USERNAME, CONF_PASSWORD, CONF_CHARGER_DN, "unique_id"}
SERIAL_SIGNALS = {455770003, 10012}  # ESN, Bluetooth name


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FusionChargeConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    state = coordinator.data

    def signals(group: dict) -> dict[str, Any]:
        return {
            str(sid): ("**REDACTED**" if sid in SERIAL_SIGNALS else dataclasses.asdict(sig))
            for sid, sig in group.items()
        }

    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "control_enabled": coordinator.control_enabled,
        "last_command": coordinator.last_command,
        "last_update_success": coordinator.last_update_success,
        "software_version": (
            state.charger.get(SIG_SOFTWARE).value if state and SIG_SOFTWARE in state.charger else None
        ),
        "state": None
        if state is None
        else {
            "connector": signals(state.connector),
            "charger": signals(state.charger),
            "working_mode": state.working_mode,
            "schedule_on": state.schedule_on,
            "plans": state.plans,
        },
    }
