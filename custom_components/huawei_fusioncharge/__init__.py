"""Huawei FusionCharge: control a Huawei SCharger through the FusionSolar cloud."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .api import FusionChargeClient
from .config_flow import PENDING_CLIENTS, take_client
from .const import (
    CARD_URL,
    CONF_CHARGER_DN,
    CONF_SUBDOMAIN,
    DOMAIN,
    STORAGE_KEY_BACKUP,
    STORAGE_KEY_SESSION,
    STORAGE_VERSION,
    VERSION,
)
from .coordinator import FusionChargeConfigEntry, FusionChargeCoordinator
from .exceptions import AuthenticationError, CaptchaRequired, FusionChargeError

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Entities of earlier versions that no longer exist (replaced by the Charge switch).
_REMOVED_KEYS = ("start_charging", "stop_charging")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card shipped with the integration and load it in the frontend."""
    await _async_register_card(hass)
    return True


async def _async_register_card(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_card"):
        return
    path = Path(__file__).parent / "frontend" / "huawei-fusioncharge-card.js"
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(path), cache_headers=False)]
        )
        add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
        hass.data[f"{DOMAIN}_card"] = True
    except Exception as err:  # noqa: BLE001 - the card is a bonus, never block the integration
        _LOGGER.warning(
            "Could not register the dashboard card (%s). Add %s as a dashboard resource instead",
            err,
            CARD_URL,
        )


async def async_setup_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> bool:
    """Set up one charger."""
    client = take_client(hass, entry.data[CONF_CHARGER_DN])
    fresh = client is None
    if client is None:
        client = FusionChargeClient(
            entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], entry.data[CONF_SUBDOMAIN]
        )

    coordinator = FusionChargeCoordinator(hass, entry, client)

    if fresh:
        # Reuse the session saved before the restart: no login, so no security code.
        saved = await coordinator.session_store.async_load()
        if client.import_session(saved):
            _LOGGER.debug("Reusing the saved FusionSolar session")
        try:
            await hass.async_add_executor_job(client.ensure_session)
        except (CaptchaRequired, AuthenticationError) as err:
            # A captcha can only be typed by the user: ask through re-authentication.
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except FusionChargeError as err:
            raise ConfigEntryNotReady(str(err)) from err

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_old_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


def _remove_old_entities(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> None:
    registry = er.async_get(hass)
    dn = entry.data[CONF_CHARGER_DN]
    for key in _REMOVED_KEYS:
        for domain in ("button",):
            entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{dn}_{key}")
            if entity_id:
                registry.async_remove(entity_id)


async def _async_reload(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> bool:
    """Unload a charger; the logged-in client is kept for a reload so no new captcha is needed."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and getattr(entry, "runtime_data", None) is not None:
        await entry.runtime_data.async_save_session()
        # Never replace a client a re-authentication has just stashed.
        hass.data.setdefault(PENDING_CLIENTS, {}).setdefault(
            entry.data[CONF_CHARGER_DN], entry.runtime_data.client
        )
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: FusionChargeConfigEntry) -> None:
    """Forget the kept client, the saved session and the plan backups."""
    take_client(hass, entry.data[CONF_CHARGER_DN])
    for key in (STORAGE_KEY_SESSION, STORAGE_KEY_BACKUP):
        await Store(hass, STORAGE_VERSION, f"{key}.{entry.entry_id}").async_remove()
