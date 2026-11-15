"""Sensors: charger status, power, energy, working mode and plans (read-only)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ChargerState, Signal
from .const import (
    SIG_CONNECTION,
    SIG_CURRENT_A,
    SIG_POWER,
    SIG_SESSION_DURATION,
    SIG_SESSION_ENERGY,
    SIG_STATUS,
    SIG_TOTAL_ENERGY,
    WORKING_MODE_OPTIONS,
)
from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity


def _numeric(signal: Signal | None) -> float | None:
    if signal is None:
        return None
    if signal.real is not None:
        return signal.real
    try:
        return float(signal.value)
    except (TypeError, ValueError):
        return None


def _text(signal: Signal | None) -> str | None:
    if signal is None or signal.value is None:
        return None
    return str(signal.value)


def _working_mode(state: ChargerState) -> str | None:
    return {"0": "normal", "1": "pv_preferred"}.get(state.working_mode or "")


@dataclass(frozen=True, kw_only=True)
class FusionChargeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ChargerState], Any]
    exists_fn: Callable[[ChargerState], bool] = lambda _: True


SENSORS: tuple[FusionChargeSensorDescription, ...] = (
    FusionChargeSensorDescription(
        key="status",
        value_fn=lambda s: _text(s.connector.get(SIG_STATUS)),
        exists_fn=lambda s: SIG_STATUS in s.connector,
    ),
    FusionChargeSensorDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        value_fn=lambda s: _numeric(s.connector.get(SIG_POWER)),
        exists_fn=lambda s: SIG_POWER in s.connector,
    ),
    FusionChargeSensorDescription(
        key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        value_fn=lambda s: _numeric(s.connector.get(SIG_CURRENT_A)),
        exists_fn=lambda s: SIG_CURRENT_A in s.connector,
    ),
    FusionChargeSensorDescription(
        key="session_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda s: _numeric(s.connector.get(SIG_SESSION_ENERGY)),
        exists_fn=lambda s: SIG_SESSION_ENERGY in s.connector,
    ),
    FusionChargeSensorDescription(
        key="session_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda s: _numeric(s.connector.get(SIG_SESSION_DURATION)),
        exists_fn=lambda s: SIG_SESSION_DURATION in s.connector,
    ),
    FusionChargeSensorDescription(
        key="total_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda s: _numeric(s.charger.get(SIG_TOTAL_ENERGY)),
        exists_fn=lambda s: SIG_TOTAL_ENERGY in s.charger,
    ),
    FusionChargeSensorDescription(
        key="connection",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: _text(s.connector.get(SIG_CONNECTION)),
        exists_fn=lambda s: SIG_CONNECTION in s.connector,
    ),
    FusionChargeSensorDescription(
        key="working_mode",
        device_class=SensorDeviceClass.ENUM,
        options=WORKING_MODE_OPTIONS,
        value_fn=_working_mode,
    ),
    FusionChargeSensorDescription(
        key="plan_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.plan_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    state = coordinator.data
    async_add_entities(
        FusionChargeSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(state)
    )


class FusionChargeSensor(FusionChargeEntity, SensorEntity):
    """A read-only value of the charger."""

    entity_description: FusionChargeSensorDescription

    def __init__(self, coordinator, description: FusionChargeSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        key = self.entity_description.key
        data = self.coordinator.data
        if key == "plan_count" and data.plans is not None:
            # Raw plans as stored by the cloud. Times are UTC; repeat_period is a
            # 7-bit day mask whose bit order is not documented by Huawei.
            return {
                "times_are_utc": True,
                "plans": [
                    {
                        "start_utc": p.get("startTime"),
                        "stop_utc": p.get("stopTime"),
                        "repeat_period": p.get("repeatPeriod"),
                        "charge_mode": p.get("chargeMode"),
                        "max_charge_power_kw": p.get("maxChargePower"),
                        "repeat": p.get("isRepeat"),
                        "valid": p.get("isValid"),
                    }
                    for p in data.plans
                ],
            }
        if key == "status":
            signal = data.connector.get(SIG_STATUS)
            return {"raw_value": signal.real} if signal else None
        if key == "working_mode" and self.coordinator.last_command:
            return {"last_command": self.coordinator.last_command}
        return None
