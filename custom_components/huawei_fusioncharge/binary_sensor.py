"""Binary sensor: is the FusionSolar schedule switched on."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ScheduleActiveSensor(entry.runtime_data, "schedule_active")])


class ScheduleActiveSensor(FusionChargeEntity, BinarySensorEntity):
    """On when the schedule ("Charge programmée") is switched on in the cloud."""

    _attr_icon = "mdi:calendar-clock"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.schedule_on is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.schedule_on
