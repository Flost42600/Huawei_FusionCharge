"""Select: working mode (signal 20002), only when commands are enabled."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import WORKING_MODE_NORMAL, WORKING_MODE_PV
from .const import WORKING_MODE_OPTIONS
from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity

_TO_CLOUD = {"normal": WORKING_MODE_NORMAL, "pv_preferred": WORKING_MODE_PV}
_FROM_CLOUD = {v: k for k, v in _TO_CLOUD.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.control_enabled:
        async_add_entities([WorkingModeSelect(coordinator, "working_mode_select")])


class WorkingModeSelect(FusionChargeEntity, SelectEntity):
    """Normal charge or PV power preferred.

    While the schedule is on, each plan's own mode applies instead.
    """

    _attr_options = WORKING_MODE_OPTIONS
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:solar-power-variant"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.working_mode in _FROM_CLOUD

    @property
    def current_option(self) -> str | None:
        return _FROM_CLOUD.get(self.coordinator.data.working_mode or "")

    async def async_select_option(self, option: str) -> None:
        coordinator = self.coordinator
        await coordinator.async_run_command(
            f"working_mode:{option}",
            coordinator.client.set_working_mode,
            coordinator.dn,
            _TO_CLOUD[option],
        )
