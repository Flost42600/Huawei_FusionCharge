"""Switches (commands enabled only): charging on/off and schedule on/off.

Charging: on = the app's "Charge now", off = stop. Its state is what the
charger reports (charging power above a small threshold); right after a
request the requested state is shown for a short while, until the cloud
confirms it or the delay runs out.

Schedule: the plans themselves are never edited. The cloud replaces the whole
plan list on every write, so the plans are read twice, backed up, resent
unchanged with only the on/off flag changed, and compared afterwards.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CHARGE_PENDING_SECONDS
from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity
from .status import is_charging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.control_enabled:
        async_add_entities(
            [ChargeSwitch(coordinator, "charge"), ScheduleSwitch(coordinator, "schedule")]
        )


class ChargeSwitch(FusionChargeEntity, SwitchEntity):
    """Charging on or off."""

    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        self._pending: tuple[bool, float] | None = None  # (requested state, deadline)
        self._last_result: str | None = None

    @property
    def available(self) -> bool:
        return super().available and (
            self._pending is not None or is_charging(self.coordinator.data) is not None
        )

    @property
    def is_on(self) -> bool | None:
        actual = is_charging(self.coordinator.data)
        if self._pending is not None:
            wanted, deadline = self._pending
            if actual == wanted:
                self._pending = None
                self._last_result = "confirmed"
            elif time.monotonic() > deadline:
                self._pending = None
                self._last_result = "not_confirmed"
                _LOGGER.warning(
                    "Charging did not %s within %d s (the car may refuse or be unplugged)",
                    "start" if wanted else "stop",
                    CHARGE_PENDING_SECONDS,
                )
            else:
                return wanted
        return actual

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "pending": self._pending[0] if self._pending else None,
            "last_result": self._last_result,
        }

    async def _async_set(self, on: bool) -> None:
        if self._pending is None and is_charging(self.coordinator.data) == on:
            return  # already in the requested state: send nothing
        coordinator = self.coordinator
        self._pending = (on, time.monotonic() + CHARGE_PENDING_SECONDS)
        self._last_result = "sent"
        self.async_write_ha_state()
        try:
            await coordinator.async_run_command(
                "start_charging" if on else "stop_charging",
                coordinator.client.start_charging if on else coordinator.client.stop_charging,
                coordinator.dn,
            )
        except Exception:
            self._pending = None
            self._last_result = "error"
            self.async_write_ha_state()
            raise

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


class ScheduleSwitch(FusionChargeEntity, SwitchEntity):
    """Charge programmée on or off."""

    _attr_icon = "mdi:calendar-clock"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.schedule_on is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.schedule_on

    async def _async_set(self, enabled: bool) -> None:
        coordinator = self.coordinator
        await coordinator.async_run_command(
            f"schedule:{'on' if enabled else 'off'}",
            coordinator.client.set_schedule_enabled,
            coordinator.dn,
            enabled,
            coordinator.make_backup_callback(),
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)
