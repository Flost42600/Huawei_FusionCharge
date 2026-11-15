"""Config flow: login with a captcha typed by the user, then pick the charger."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FusionChargeClient, normalize_subdomain
from .captcha_view import drop_captchas, register_captcha
from .const import (
    CONF_CAPTCHA,
    CONF_CHARGER_DN,
    CONF_CHARGER_NAME,
    CONF_SUBDOMAIN,
    DEFAULT_CONTROL_INTERVAL,
    DEFAULT_ENABLE_CONTROL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OPT_CONTROL_INTERVAL,
    OPT_ENABLE_CONTROL,
    OPT_SCAN_INTERVAL,
)
from .exceptions import (
    AuthenticationError,
    CannotConnect,
    CaptchaRequired,
    FusionChargeError,
    InvalidCaptcha,
)

_LOGGER = logging.getLogger(__name__)

PENDING_CLIENTS = f"{DOMAIN}_pending_clients"


def stash_client(hass, key: str, client: FusionChargeClient) -> None:
    """Hand the logged-in client to async_setup_entry, so no second login (and captcha) is needed."""
    hass.data.setdefault(PENDING_CLIENTS, {})[key] = client


def take_client(hass, key: str) -> FusionChargeClient | None:
    return hass.data.get(PENDING_CLIENTS, {}).pop(key, None)


class FusionChargeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Huawei FusionCharge."""

    VERSION = 1

    def __init__(self) -> None:
        self._client: FusionChargeClient | None = None
        self._login: dict[str, str] = {}
        self._chargers: list[dict[str, str]] = []
        self._captcha_url: str | None = None
        self._return_step = "user"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FusionChargeOptionsFlow()

    # -------------------------------------------------------------- user step

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                subdomain = normalize_subdomain(user_input[CONF_SUBDOMAIN])
            except ValueError:
                errors[CONF_SUBDOMAIN] = "invalid_subdomain"
            else:
                self._login = {
                    CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_SUBDOMAIN: subdomain,
                }
                self._return_step = "user"
                return await self._async_try_login(None)
        return self._show_user_form(errors, user_input)

    def _show_user_form(
        self, errors: dict[str, str], user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        values = user_input or self._login
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=values.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_SUBDOMAIN, default=values.get(CONF_SUBDOMAIN, "")): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ----------------------------------------------------------- captcha step

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._async_try_login(user_input[CONF_CAPTCHA])
        return self._show_captcha_form({})

    def _show_captcha_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema({vol.Required(CONF_CAPTCHA): str}),
            errors=errors,
            description_placeholders={"captcha_url": self._captcha_url or ""},
        )

    # ------------------------------------------------------------------ login

    async def _async_try_login(self, code: str | None) -> ConfigFlowResult:
        if code is None or self._client is None:
            self._client = FusionChargeClient(
                self._login[CONF_USERNAME],
                self._login[CONF_PASSWORD],
                self._login[CONF_SUBDOMAIN],
            )
        errors: dict[str, str] = {}
        try:
            await self.hass.async_add_executor_job(self._client.login, code)
        except InvalidCaptcha as err:
            self._captcha_url = register_captcha(self.hass, err.image)
            return self._show_captcha_form({"base": "invalid_captcha"})
        except CaptchaRequired as err:
            self._captcha_url = register_captcha(self.hass, err.image)
            return self._show_captcha_form({})
        except AuthenticationError:
            errors["base"] = "invalid_auth"
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except FusionChargeError:
            _LOGGER.exception("Unexpected FusionSolar error during login")
            errors["base"] = "unknown"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during login")
            errors["base"] = "unknown"

        if errors:
            self._client = None
            if self._return_step == "reauth_confirm":
                return self._show_reauth_form(errors)
            return self._show_user_form(errors)

        drop_captchas(self.hass)
        if self._return_step == "reauth_confirm":
            return await self._async_finish_reauth()
        return await self._async_after_login()

    async def _async_after_login(self) -> ConfigFlowResult:
        assert self._client is not None
        try:
            self._chargers = await self.hass.async_add_executor_job(self._client.list_chargers)
        except FusionChargeError:
            _LOGGER.exception("Could not list the chargers")
            return self.async_abort(reason="cannot_connect")
        if not self._chargers:
            return self.async_abort(reason="no_chargers")
        if len(self._chargers) == 1:
            return await self._async_create(self._chargers[0])
        return await self.async_step_pick_charger()

    async def async_step_pick_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            charger = next(c for c in self._chargers if c["dn"] == user_input[CONF_CHARGER_DN])
            return await self._async_create(charger)
        options = [SelectOptionDict(value=c["dn"], label=c["name"]) for c in self._chargers]
        return self.async_show_form(
            step_id="pick_charger",
            data_schema=vol.Schema(
                {vol.Required(CONF_CHARGER_DN): SelectSelector(SelectSelectorConfig(options=options))}
            ),
        )

    async def _async_create(self, charger: dict[str, str]) -> ConfigFlowResult:
        await self.async_set_unique_id(charger["dn"])
        self._abort_if_unique_id_configured()
        assert self._client is not None
        stash_client(self.hass, charger["dn"], self._client)
        return self.async_create_entry(
            title=charger["name"],
            data={
                **self._login,
                CONF_CHARGER_DN: charger["dn"],
                CONF_CHARGER_NAME: charger["name"],
            },
            options={
                OPT_ENABLE_CONTROL: DEFAULT_ENABLE_CONTROL,
                OPT_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                OPT_CONTROL_INTERVAL: DEFAULT_CONTROL_INTERVAL,
            },
        )

    # ------------------------------------------------------------------ reauth

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._login = {
            CONF_USERNAME: entry_data[CONF_USERNAME],
            CONF_PASSWORD: entry_data[CONF_PASSWORD],
            CONF_SUBDOMAIN: entry_data[CONF_SUBDOMAIN],
        }
        self._return_step = "reauth_confirm"
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._login[CONF_PASSWORD] = user_input[CONF_PASSWORD]
            return await self._async_try_login(None)
        return self._show_reauth_form({})

    def _show_reauth_form(self, errors: dict[str, str]) -> ConfigFlowResult:
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
            description_placeholders={"username": self._login.get(CONF_USERNAME, "")},
        )

    async def _async_finish_reauth(self) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        assert self._client is not None
        stash_client(self.hass, entry.data[CONF_CHARGER_DN], self._client)
        return self.async_update_reload_and_abort(
            entry, data_updates={CONF_PASSWORD: self._login[CONF_PASSWORD]}
        )


class FusionChargeOptionsFlow(OptionsFlow):
    """Commands on/off and polling intervals."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    OPT_ENABLE_CONTROL,
                    default=options.get(OPT_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL),
                ): bool,
                vol.Required(
                    OPT_SCAN_INTERVAL,
                    default=options.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                vol.Required(
                    OPT_CONTROL_INTERVAL,
                    default=options.get(OPT_CONTROL_INTERVAL, DEFAULT_CONTROL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
