"""Binary sensors: schedule state and connection health (for alarms)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity
from .status import charger_online, is_plugged


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            ScheduleActiveSensor(coordinator, "schedule_active"),
            CloudConnectedSensor(coordinator, "cloud_connected"),
            ChargerOnlineSensor(coordinator, "charger_online"),
            ReauthNeededSensor(coordinator, "reauth_needed"),
            VehiclePluggedSensor(coordinator, "vehicle_plugged"),
        ]
    )


class ScheduleActiveSensor(FusionChargeEntity, BinarySensorEntity):
    """On when the schedule ("Charge programmée") is switched on in the cloud."""

    _attr_icon = "mdi:calendar-clock"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.schedule_on is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.schedule_on


class CloudConnectedSensor(FusionChargeEntity, BinarySensorEntity):
    """Home Assistant reaches the FusionSolar cloud. Never unavailable: off is the alarm."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success) and not self.coordinator.auth_failed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coordinator = self.coordinator
        return {
            "last_success": coordinator.last_success.isoformat() if coordinator.last_success else None,
            "last_error": coordinator.last_error,
        }


class ChargerOnlineSensor(FusionChargeEntity, BinarySensorEntity):
    """The charger itself is connected to the cloud (signal 19999, or the device tree)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool | None:
        return charger_online(self.coordinator.data)[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return charger_online(self.coordinator.data)[1]


class VehiclePluggedSensor(FusionChargeEntity, BinarySensorEntity):
    """A vehicle is plugged in, deduced from the charger status code."""

    _attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def available(self) -> bool:
        return super().available and is_plugged(self.coordinator.data) is not None

    @property
    def is_on(self) -> bool | None:
        return is_plugged(self.coordinator.data)


class ReauthNeededSensor(FusionChargeEntity, BinarySensorEntity):
    """On when Huawei asks for the password or a security code again. Never unavailable."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.auth_failed
