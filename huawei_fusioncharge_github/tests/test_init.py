"""Config flow, setup and entities, with a fake client (no network)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.huawei_fusioncharge.api import ChargerState, Signal
from custom_components.huawei_fusioncharge.const import (
    CONF_CHARGER_DN,
    CONF_CHARGER_NAME,
    CONF_SUBDOMAIN,
    DOMAIN,
    OPT_ENABLE_CONTROL,
)
from custom_components.huawei_fusioncharge.exceptions import (
    AuthenticationError,
    CaptchaRequired,
    InvalidCaptcha,
)

DN = "NE=12345"


class FakeClient:
    """Stands in for FusionChargeClient."""

    captcha_on_login = False
    fail_state_with: Exception | None = None

    def __init__(self, username, password, subdomain, session=None):
        self.username = username
        self.password = password
        self.calls: list[tuple] = []
        self.schedule_on = True
        self.mode = "1"

    def login(self, verify_code=None):
        self.calls.append(("login", verify_code))
        if self.password == "bad":
            raise AuthenticationError("bad password")
        if FakeClient.captcha_on_login and verify_code is None:
            raise CaptchaRequired(b"\x89PNGcaptcha")
        if verify_code == "wrong":
            raise InvalidCaptcha(b"\x89PNGagain")

    def list_chargers(self):
        return [{"dn": DN, "name": "Borne garage"}]

    def get_state(self, dn, include_control=True):
        if FakeClient.fail_state_with:
            raise FakeClient.fail_state_with
        state = ChargerState(
            connector={
                10004: Signal("Charging", 3.0),
                10013: Signal("7.0", 7.0),
                10035: Signal("4.2", 4.2),
                19999: Signal("Connected", 1.0),
            },
            charger={10001: Signal("V100R023C10SPC231", None), 10007: Signal("SCharger-7KS-S0", None)},
        )
        if include_control:
            state.working_mode = self.mode
            state.schedule_on = self.schedule_on
            state.plans = []
            state.plan_count = 0
            state.control_read = True
        return state

    def start_charging(self, dn):
        self.calls.append(("start", dn))

    def stop_charging(self, dn):
        self.calls.append(("stop", dn))

    def arm_schedule(self, dn):
        self.calls.append(("arm", dn))

    def set_working_mode(self, dn, mode):
        self.calls.append(("mode", mode))
        self.mode = mode

    def set_schedule_enabled(self, dn, enabled, backup=None):
        self.calls.append(("schedule", enabled))
        if backup:
            backup([], self.schedule_on)
        self.schedule_on = enabled


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every Home Assistant test."""
    yield


@pytest.fixture(autouse=True)
def fake_client():
    FakeClient.captcha_on_login = False
    FakeClient.fail_state_with = None
    with patch("custom_components.huawei_fusioncharge.config_flow.FusionChargeClient", FakeClient), \
         patch("custom_components.huawei_fusioncharge.FusionChargeClient", FakeClient):
        yield


def make_entry(control: bool) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DN,
        title="Borne garage",
        data={
            CONF_USERNAME: "me",
            CONF_PASSWORD: "pw",
            CONF_SUBDOMAIN: "uni004eu5",
            CONF_CHARGER_DN: DN,
            CONF_CHARGER_NAME: "Borne garage",
        },
        options={OPT_ENABLE_CONTROL: control, "scan_interval": 30, "control_interval": 60},
    )


async def setup(hass: HomeAssistant, control: bool) -> MockConfigEntry:
    entry = make_entry(control)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --------------------------------------------------------------- config flow


async def test_flow_with_captcha_typed_by_user(hass: HomeAssistant):
    FakeClient.captcha_on_login = True
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "me", CONF_PASSWORD: "pw", CONF_SUBDOMAIN: "uni004eu5.fusionsolar.huawei.com"},
    )
    assert result["step_id"] == "captcha"
    assert result["description_placeholders"]["captcha_url"].startswith(
        f"/api/{DOMAIN}/captcha/"
    )

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"captcha": "wrong"})
    assert result["step_id"] == "captcha"
    assert result["errors"] == {"base": "invalid_captcha"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"captcha": "ab12"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Borne garage"
    assert result["data"][CONF_SUBDOMAIN] == "uni004eu5"
    assert result["data"][CONF_CHARGER_DN] == DN
    assert result["options"][OPT_ENABLE_CONTROL] is False
    await hass.async_block_till_done()


async def test_captcha_image_is_served(hass: HomeAssistant, hass_client_no_auth):
    FakeClient.captcha_on_login = True
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "me", CONF_PASSWORD: "pw", CONF_SUBDOMAIN: "uni004eu5"}
    )
    client = await hass_client_no_auth()
    resp = await client.get(result["description_placeholders"]["captcha_url"])
    assert resp.status == 200
    assert resp.content_type == "image/png"
    assert await resp.read() == b"\x89PNGcaptcha"
    assert (await client.get(f"/api/{DOMAIN}/captcha/unknown")).status == 404


async def test_flow_bad_password(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "me", CONF_PASSWORD: "bad", CONF_SUBDOMAIN: "uni004eu5"}
    )
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_flow_bad_subdomain(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_USERNAME: "me", CONF_PASSWORD: "pw", CONF_SUBDOMAIN: "a b"}
    )
    assert result["errors"] == {CONF_SUBDOMAIN: "invalid_subdomain"}


# ------------------------------------------------------------------ entities


async def test_read_only_by_default(hass: HomeAssistant):
    await setup(hass, control=False)
    assert hass.states.get("sensor.borne_garage_charging_power").state == "7.0"
    assert hass.states.get("sensor.borne_garage_status").state == "Charging"
    assert hass.states.get("binary_sensor.borne_garage_schedule_active").state == "on"
    assert hass.states.get("sensor.borne_garage_current_working_mode").state == "pv_preferred"
    assert hass.states.get("button.borne_garage_start_charging") is None
    assert hass.states.get("switch.borne_garage_scheduled_charging") is None
    assert hass.states.get("select.borne_garage_working_mode") is None


async def test_commands_when_enabled(hass: HomeAssistant):
    entry = await setup(hass, control=True)
    client = entry.runtime_data.client

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.borne_garage_start_charging"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.borne_garage_stop_charging"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.borne_garage_arm_schedule"}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.borne_garage_working_mode", "option": "normal"}, blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.borne_garage_scheduled_charging"}, blocking=True
    )
    await hass.async_block_till_done()

    assert ("start", DN) in client.calls
    assert ("stop", DN) in client.calls
    assert ("arm", DN) in client.calls
    assert ("mode", "0") in client.calls
    assert ("schedule", False) in client.calls
    assert hass.states.get("switch.borne_garage_scheduled_charging").state == "off"
    assert hass.states.get("select.borne_garage_working_mode").state == "normal"


async def test_command_error_is_reported(hass: HomeAssistant):
    from custom_components.huawei_fusioncharge.exceptions import UnsafeOperation

    entry = await setup(hass, control=True)

    def refuse(dn, enabled, backup=None):
        raise UnsafeOperation("A one-time plan exists")

    entry.runtime_data.client.set_schedule_enabled = refuse
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": "switch.borne_garage_scheduled_charging"},
            blocking=True,
        )


async def test_auth_failure_starts_reauth(hass: HomeAssistant):
    FakeClient.fail_state_with = CaptchaRequired(b"img")
    entry = make_entry(control=False)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
