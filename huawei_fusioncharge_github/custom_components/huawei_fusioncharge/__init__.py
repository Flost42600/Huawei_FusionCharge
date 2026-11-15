"""Huawei FusionCharge: control a Huawei SCharger through the FusionSolar cloud."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import FusionChargeClient
from .config_flow import PENDING_CLIENTS, take_client
from .const import CONF_CHARGER_DN, CONF_SUBDOMAIN, DOMAIN
from .coordinator import FusionChargeConfigEntry, FusionChargeCoordinator
from .exceptions import AuthenticationError, CannotConnect, CaptchaRequired, FusionChargeError

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> bool:
    """Set up one charger."""
    client = take_client(hass, entry.data[CONF_CHARGER_DN])
    if client is None:
        client = FusionChargeClient(
            entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], entry.data[CONF_SUBDOMAIN]
        )
        try:
            await hass.async_add_executor_job(client.login)
        except (CaptchaRequired, AuthenticationError) as err:
            # A captcha can only be typed by the user: ask through re-authentication.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except (CannotConnect, FusionChargeError) as err:
            raise ConfigEntryNotReady(str(err)) from err

    coordinator = FusionChargeCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> bool:
    """Unload a charger; the logged-in client is kept for a reload so no new captcha is needed."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and getattr(entry, "runtime_data", None) is not None:
        # Never replace a client a re-authentication has just stashed.
        hass.data.setdefault(PENDING_CLIENTS, {}).setdefault(
            entry.data[CONF_CHARGER_DN], entry.runtime_data.client
        )
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> None:
    """Forget the kept client when the charger is removed."""
    take_client(hass, entry.data[CONF_CHARGER_DN])
