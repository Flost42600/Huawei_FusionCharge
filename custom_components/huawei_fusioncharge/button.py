"""Buttons: start charging, stop charging, arm the schedule (commands enabled only)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FusionChargeClient
from .coordinator import FusionChargeConfigEntry
from .entity import FusionChargeEntity


@dataclass(frozen=True, kw_only=True)
class FusionChargeButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[FusionChargeClient], Callable[[str], Any]]


BUTTONS: tuple[FusionChargeButtonDescription, ...] = (
    # The app's "Charge now": starts right away, even outside the plans.
    FusionChargeButtonDescription(
        key="start_charging", icon="mdi:play", press_fn=lambda c: c.start_charging
    ),
    FusionChargeButtonDescription(
        key="stop_charging", icon="mdi:stop", press_fn=lambda c: c.stop_charging
    ),
    # The app's "Schedule": the charger waits for the plans instead of charging now.
    FusionChargeButtonDescription(
        key="arm_schedule", icon="mdi:calendar-check", press_fn=lambda c: c.arm_schedule
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FusionChargeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.control_enabled:
        async_add_entities(FusionChargeButton(coordinator, d) for d in BUTTONS)


class FusionChargeButton(FusionChargeEntity, ButtonEntity):
    """Sends one charge command. The car still decides whether it charges."""

    entity_description: FusionChargeButtonDescription

    def __init__(self, coordinator, description: FusionChargeButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        coordinator = self.coordinator
        await coordinator.async_run_command(
            self.entity_description.key,
            self.entity_description.press_fn(coordinator.client),
            coordinator.dn,
        )
