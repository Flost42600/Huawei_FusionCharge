"""Base entity for the FusionCharge charger."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, SIG_HARDWARE, SIG_MODEL, SIG_SOFTWARE
from .coordinator import FusionChargeCoordinator


class FusionChargeEntity(CoordinatorEntity[FusionChargeCoordinator]):
    """Every entity belongs to the one charger device of its entry."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FusionChargeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.dn}_{key}"
        charger = coordinator.data.charger if coordinator.data else {}

        def text(signal_id: int) -> str | None:
            signal = charger.get(signal_id)
            return str(signal.value) if signal and signal.value is not None else None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.dn)},
            name=coordinator.config_entry.title,
            manufacturer=MANUFACTURER,
            model=text(SIG_MODEL) or "SCharger",
            sw_version=text(SIG_SOFTWARE),
            hw_version=text(SIG_HARDWARE),
        )
