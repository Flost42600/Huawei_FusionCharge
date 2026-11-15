"""Switch: schedule on/off, only when commands are enabled.

The plans themselves are never edited: the cloud replaces the whole plan list
on every write, so the plans are read twice, backed up, resent unchanged with
only the on/off flag changed, and compared afterwards.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.control_enabled:
        async_add_entities([ScheduleSwitch(coordinator, "schedule")])


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
