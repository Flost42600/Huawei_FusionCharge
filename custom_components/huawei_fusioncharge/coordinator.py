"""Polling and command execution for one FusionCharge charger."""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ChargerState, FusionChargeClient
from .const import (
    BACKUP_KEEP,
    CONF_CHARGER_DN,
    DEFAULT_CONTROL_INTERVAL,
    DEFAULT_ENABLE_CONTROL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPT_CONTROL_INTERVAL,
    OPT_ENABLE_CONTROL,
    OPT_SCAN_INTERVAL,
    STORAGE_KEY_BACKUP,
    STORAGE_VERSION,
)
from .exceptions import (
    AuthenticationError,
    CannotConnect,
    CaptchaRequired,
    CommandNotConfirmed,
    FusionChargeError,
    UnsafeOperation,
)

_LOGGER = logging.getLogger(__name__)

type FusionChargeConfigEntry = ConfigEntry["FusionChargeCoordinator"]


class FusionChargeCoordinator(DataUpdateCoordinator[ChargerState]):
    """Reads the charger and runs the commands, one at a time."""

    config_entry: FusionChargeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: FusionChargeConfigEntry, client: FusionChargeClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(
                seconds=entry.options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.dn: str = entry.data[CONF_CHARGER_DN]
        self.control_enabled: bool = entry.options.get(OPT_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)
        self._control_interval = entry.options.get(OPT_CONTROL_INTERVAL, DEFAULT_CONTROL_INTERVAL)
        self._last_control_read = 0.0
        self._force_control = True
        self._backup_store: Store[list[dict]] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_BACKUP}.{entry.entry_id}"
        )
        self._pending_backups: list[dict] = []
        self.last_command: dict[str, Any] | None = None

    async def _async_update_data(self) -> ChargerState:
        now = time.monotonic()
        include_control = (
            self._force_control or now - self._last_control_read >= self._control_interval
        )
        try:
            state = await self.hass.async_add_executor_job(
                self.client.get_state, self.dn, include_control
            )
        except (CaptchaRequired, AuthenticationError) as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except CannotConnect as err:
            raise UpdateFailed(f"FusionSolar unreachable: {err}") from err
        except FusionChargeError as err:
            raise UpdateFailed(f"FusionSolar error: {err}") from err

        if state.control_read:
            self._last_control_read = now
            self._force_control = False
        elif self.data is not None:
            # Keep the last known control values between control reads.
            state = dataclasses.replace(
                state,
                working_mode=self.data.working_mode,
                schedule_on=self.data.schedule_on,
                plans=self.data.plans,
                plan_count=self.data.plan_count,
                plan_meta=self.data.plan_meta,
            )
        return state

    # ------------------------------------------------------------------ commands

    async def async_run_command(self, name: str, func: Callable[..., Any], *args: Any) -> Any:
        """Run one blocking client command, map its errors, then re-read everything."""
        if not self.control_enabled:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="control_disabled"
            )
        result: Any = None
        outcome = "ok"
        try:
            result = await self.hass.async_add_executor_job(func, *args)
        except (CaptchaRequired, AuthenticationError) as err:
            outcome = "auth"
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except UnsafeOperation as err:
            outcome = "refused"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unsafe",
                translation_placeholders={"reason": str(err)},
            ) from err
        except CommandNotConfirmed as err:
            outcome = "not_confirmed"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_confirmed",
                translation_placeholders={"reason": str(err)},
            ) from err
        except FusionChargeError as err:
            outcome = "error"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"reason": str(err)},
            ) from err
        finally:
            self.last_command = {
                "command": name,
                "outcome": outcome,
                "time": dt_util.utcnow().isoformat(),
            }
            await self._async_flush_backups()
            # Re-read now (not debounced) so the entities show what the cloud reports.
            self._force_control = True
            await self.async_refresh()
        return result

    def make_backup_callback(self) -> Callable[[list[dict], bool], None]:
        """Callback for the executor thread; saved to .storage after the command."""

        def _backup(plans: list[dict], was_on: bool) -> None:
            self._pending_backups.append(
                {
                    "time": dt_util.utcnow().isoformat(),
                    "switch_on": was_on,
                    "plans": plans,
                }
            )

        return _backup

    async def _async_flush_backups(self) -> None:
        if not self._pending_backups:
            return
        new, self._pending_backups = self._pending_backups, []
        try:
            existing = await self._backup_store.async_load() or []
            await self._backup_store.async_save((existing + new)[-BACKUP_KEEP:])
        except Exception as err:  # noqa: BLE001 - a backup failure must not hide the command result
            _LOGGER.error("Could not save the plan backup: %r", err)
