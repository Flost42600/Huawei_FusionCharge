"""Tests of the blocking cloud client, with a fake HTTP session (no network)."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import pytest

from custom_components.huawei_fusioncharge import api
from custom_components.huawei_fusioncharge.exceptions import (
    AuthenticationError,
    CaptchaRequired,
    CloudError,
    CommandNotConfirmed,
    InvalidCaptcha,
    UnsafeOperation,
)

BASE = "https://uni004eu5.fusionsolar.huawei.com"
LOGIN = "https://eu5.fusionsolar.huawei.com"
HOME = "/rest/neteco/web/homemgr/v1"

# Real query-plan answer captured from the FusionSolar app (fork Matthias2703).
REAL_PLANS = [
    {"isValid": True, "isRepeat": True, "repeatPeriod": 62, "startTime": "15:00",
     "stopTime": "04:00", "chargeMode": 0, "maxChargePower": 11.0},
    {"isValid": True, "isRepeat": True, "repeatPeriod": 127, "startTime": "05:00",
     "stopTime": "14:00", "chargeMode": 1, "maxChargePower": 11.0},
]


class FakeResponse:
    def __init__(self, body: Any = None, status: int = 200, text: str | None = None,
                 content: bytes | None = None, url: str = "") -> None:
        self.status_code = status
        self.url = url
        if content is not None:
            self.content = content
            self.text = ""
        elif text is not None:
            self.content = text.encode()
            self.text = text
        elif body is None:
            self.content = b""
            self.text = ""
        else:
            self.text = json.dumps(body)
            self.content = self.text.encode()
        self._body = body

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Answers by (method, url without query); a list answers in order, the last one repeats."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.routes: dict[tuple[str, str], Any] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self._count: dict[tuple[str, str], int] = defaultdict(int)

    def on(self, method: str, url: str, *answers: Any) -> None:
        self.routes[(method, url)] = list(answers)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        key = (method, url)
        self.calls.append((method, url, kwargs))
        if key not in self.routes:
            raise AssertionError(f"Unexpected request {method} {url}")
        answers = self.routes[key]
        index = min(self._count[key], len(answers) - 1)
        self._count[key] += 1
        answer = answers[index]
        if callable(answer):
            answer = answer(kwargs)
        if not isinstance(answer, FakeResponse):
            answer = FakeResponse(answer)
        answer.url = url
        return answer

    def posted(self, url: str) -> list[dict]:
        return [kw.get("json") for m, u, kw in self.calls if m == "POST" and u == url]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(api, "_sleep", lambda _s: None)


def logged_in_client(session: FakeSession) -> api.FusionChargeClient:
    """A client whose session is alive, with the charger ids resolvable."""
    session.on("GET", f"{BASE}/rest/dpcloud/auth/v1/is-session-alive", {"code": 0})
    session.on("GET", f"{BASE}/rest/dpcloud/auth/v1/keep-alive", {"code": 0, "payload": "csrf"})
    session.on("POST", f"{BASE}/rest/dp/pvms/organization/v1/tree",
               {"childList": [{"elementId": "111"}]})
    session.on("GET", f"{BASE}/rest/pvms/web/device/v1/mo-details",
               {"data": {"mo": {"dnId": 222}}})
    client = api.FusionChargeClient("user", "secret", "uni004eu5", session=session)
    client._company_dn = "NE=1"
    return client


def add_login_routes(session: FakeSession, show_captcha: bool) -> None:
    session.on("GET", f"{LOGIN}/unisso/config", {"showVerifyCode": show_captcha})
    session.on("GET", f"{LOGIN}/unisso/verifycode", FakeResponse(content=b"\x89PNG-image"))
    session.on("GET", f"{LOGIN}/unisso/pubkey", {"enableEncrypt": False})
    session.on("POST", f"{LOGIN}/unisso/v2/validateUser.action",
               {"errorCode": "0", "errorMsg": ""})
    session.on("GET", f"{BASE}/rest/dpcloud/auth/v1/keep-alive", {"code": 0, "payload": "csrf"})
    session.on("GET", f"{BASE}/rest/neteco/web/organization/v2/company/current",
               {"data": {"moDn": "NE=1"}})


# ------------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("uni004eu5", "uni004eu5"),
        ("https://uni004eu5.fusionsolar.huawei.com/pvmswebsite/", "uni004eu5"),
        ("UNI004EU5.fusionsolar.huawei.com", "uni004eu5"),
    ],
)
def test_normalize_subdomain(raw, expected):
    assert api.normalize_subdomain(raw) == expected


def test_normalize_subdomain_rejects_garbage():
    with pytest.raises(ValueError):
        api.normalize_subdomain("evil.com/@x")


def test_plan_to_request_matches_the_app():
    sent = api.plan_to_request(REAL_PLANS[0])
    assert sent["calculatedStartTime"] == 1500
    assert sent["calculatedStopTime"] == 400
    assert sent["repeat"] is True and sent["valid"] is True
    assert api.plan_signature([sent]) == api.plan_signature([REAL_PLANS[0]])


# -------------------------------------------------------------------- login


def test_login_without_captcha(monkeypatch):
    session = FakeSession()
    add_login_routes(session, show_captcha=False)
    client = api.FusionChargeClient("user", "secret", "uni004eu5", session=session)
    monkeypatch.setattr(api, "_new_session", lambda: session)
    client.login()
    assert client._company_dn == "NE=1"
    assert session.headers["roarand"] == "csrf"
    body = session.posted(f"{LOGIN}/unisso/v2/validateUser.action")[0]
    assert "verifycode" not in body


def test_captcha_is_returned_to_the_user_then_used(monkeypatch):
    session = FakeSession()
    add_login_routes(session, show_captcha=True)
    session.on("POST", f"{LOGIN}/unisso/preValidVerifycode", FakeResponse(text="success"))
    monkeypatch.setattr(api, "_new_session", lambda: session)
    client = api.FusionChargeClient("user", "secret", "uni004eu5")

    with pytest.raises(CaptchaRequired) as err:
        client.login()
    assert err.value.image == b"\x89PNG-image"
    assert not session.posted(f"{LOGIN}/unisso/v2/validateUser.action")

    client.login("ab12")
    body = session.posted(f"{LOGIN}/unisso/v2/validateUser.action")[0]
    assert body["verifycode"] == "ab12"


def test_wrong_captcha_gives_a_new_image(monkeypatch):
    session = FakeSession()
    add_login_routes(session, show_captcha=True)
    session.on("POST", f"{LOGIN}/unisso/preValidVerifycode", FakeResponse(text="fail"))
    monkeypatch.setattr(api, "_new_session", lambda: session)
    client = api.FusionChargeClient("user", "secret", "uni004eu5")
    with pytest.raises(InvalidCaptcha) as err:
        client.login("zzzz")
    assert err.value.image == b"\x89PNG-image"


def test_wrong_password(monkeypatch):
    session = FakeSession()
    add_login_routes(session, show_captcha=False)
    session.on("POST", f"{LOGIN}/unisso/v2/validateUser.action",
               {"errorCode": "406", "errorMsg": "Incorrect user name or password."})
    monkeypatch.setattr(api, "_new_session", lambda: session)
    client = api.FusionChargeClient("user", "bad", "uni004eu5")
    with pytest.raises(AuthenticationError):
        client.login()


def test_expired_session_needing_a_captcha_is_not_solved(monkeypatch):
    session = FakeSession()
    add_login_routes(session, show_captcha=True)
    session.on("GET", f"{BASE}/rest/dpcloud/auth/v1/is-session-alive", {"code": 1})
    monkeypatch.setattr(api, "_new_session", lambda: session)
    client = api.FusionChargeClient("user", "secret", "uni004eu5", session=session)
    client._company_dn = "NE=1"
    with pytest.raises(CaptchaRequired):
        client.ensure_session()


# -------------------------------------------------------------------- reads


def test_get_state_splits_groups_and_reads_control():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/device/get-realtime-info", {
        "111": [{"id": 10004, "value": "Charging", "realValue": "3"},
                {"id": 10013, "value": "7.01", "realValue": "7.01"},
                {"id": 10001, "value": "1"}],
        "222": [{"id": 10001, "value": "V100R023C10SPC231"},
                {"id": 10008, "value": "1234.5", "realValue": "1234.5"}],
    })
    session.on("POST", f"{BASE}{HOME}/device/get-config-info",
               {"111": [{"id": 20002, "value": "1"}]})
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan",
               {"switchOn": 1, "plans": REAL_PLANS})

    state = client.get_state("NE=charger")
    assert state.connector[10004].value == "Charging"
    assert state.connector[10013].real == pytest.approx(7.01)
    assert state.charger[10001].value == "V100R023C10SPC231"
    assert state.working_mode == "1"
    assert state.schedule_on is True
    assert state.plan_count == 2
    assert state.control_read is True


def test_missing_switch_on_is_unknown_not_off():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/device/get-realtime-info", {"111": [{"id": 10004, "value": "Idle"}]})
    session.on("POST", f"{BASE}{HOME}/device/get-config-info", {"111": [{"id": 20002, "value": "0"}]})
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan", {"plans": []})
    state = client.get_state("NE=charger")
    assert state.schedule_on is None
    assert state.control_read is False
    assert state.connector[10004].value == "Idle"


def test_error_inside_http_200_is_an_error():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/device/get-realtime-info", {"exceptionId": "bad status"})
    with pytest.raises(CloudError):
        client.get_state("NE=charger", include_control=False)


# ------------------------------------------------------------------- writes


def test_working_mode_written_to_connector_and_confirmed():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/device/get-config-info",
               {"111": [{"id": 20002, "value": "0"}]},
               {"111": [{"id": 20002, "value": "1"}]})
    session.on("POST", f"{BASE}{HOME}/device/set-config-info", FakeResponse())
    client.set_working_mode("NE=charger", "1")
    sent = session.posted(f"{BASE}{HOME}/device/set-config-info")
    assert sent == [{"changeValues": [{"id": "20002", "value": "1"}], "dnId": 111}]


def test_working_mode_not_confirmed_raises():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/device/get-config-info", {"111": [{"id": 20002, "value": "0"}]})
    session.on("POST", f"{BASE}{HOME}/device/set-config-info", FakeResponse())
    with pytest.raises(CommandNotConfirmed):
        client.set_working_mode("NE=charger", "1")
    assert len(session.posted(f"{BASE}{HOME}/device/set-config-info")) == 2


def test_working_mode_rejects_unknown_value():
    client = logged_in_client(FakeSession())
    with pytest.raises(ValueError):
        client.set_working_mode("NE=charger", "2")


def test_start_charging_payload_and_empty_body():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/charger/charge/start-charge", FakeResponse())
    assert client.start_charging("NE=charger") is None
    assert session.posted(f"{BASE}{HOME}/charger/charge/start-charge") == [
        {"accountId": "", "gunNumber": 1, "dnId": 222}
    ]


def test_command_error_code_raises():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/charger/charge/stop-charge", {"code": 5, "description": "busy"})
    with pytest.raises(CloudError):
        client.stop_charging("NE=charger")


def test_arm_schedule_payload():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("POST", f"{BASE}{HOME}/charger/auth/confirm-auth", {"chargeStatus": 10})
    assert client.arm_schedule("NE=charger") == 10
    assert session.posted(f"{BASE}{HOME}/charger/auth/confirm-auth") == [
        {"accountId": "", "authType": 0, "gunNumber": 1, "dnId": 222}
    ]


# ----------------------------------------------------------------- schedule


def test_schedule_on_resends_plans_unchanged_and_backs_up():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan",
               {"switchOn": 0, "plans": REAL_PLANS},
               {"switchOn": 0, "plans": REAL_PLANS},
               {"switchOn": 1, "plans": REAL_PLANS})
    session.on("POST", f"{BASE}{HOME}/charger/plan/config-plan", FakeResponse())
    backups = []
    client.set_schedule_enabled("NE=charger", True, lambda p, on: backups.append((p, on)))

    sent = session.posted(f"{BASE}{HOME}/charger/plan/config-plan")
    assert len(sent) == 1
    assert sent[0]["switchOn"] == 1 and sent[0]["dnId"] == 222
    assert api.plan_signature(sent[0]["plans"]) == api.plan_signature(REAL_PLANS)
    assert backups == [(REAL_PLANS, False)]


def test_schedule_already_in_state_writes_nothing():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan", {"switchOn": 1, "plans": REAL_PLANS})
    client.set_schedule_enabled("NE=charger", True)
    assert not session.posted(f"{BASE}{HOME}/charger/plan/config-plan")


def test_schedule_refused_when_plans_change_between_reads():
    session = FakeSession()
    client = logged_in_client(session)
    changed = [dict(REAL_PLANS[0], stopTime="05:00"), REAL_PLANS[1]]
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan",
               {"switchOn": 0, "plans": REAL_PLANS}, {"switchOn": 0, "plans": changed})
    with pytest.raises(UnsafeOperation):
        client.set_schedule_enabled("NE=charger", True)
    assert not session.posted(f"{BASE}{HOME}/charger/plan/config-plan")


def test_schedule_refused_with_one_time_plan():
    session = FakeSession()
    client = logged_in_client(session)
    plans = [dict(REAL_PLANS[0], isRepeat=False, startTime="1790000000000")]
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan", {"switchOn": 1, "plans": plans})
    with pytest.raises(UnsafeOperation):
        client.set_schedule_enabled("NE=charger", False)


def test_schedule_on_refused_without_plans():
    session = FakeSession()
    client = logged_in_client(session)
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan", {"switchOn": 0, "plans": []})
    with pytest.raises(UnsafeOperation):
        client.set_schedule_enabled("NE=charger", True)


def test_schedule_restores_when_plans_come_back_different():
    session = FakeSession()
    client = logged_in_client(session)
    lost = {"switchOn": 1, "plans": []}
    session.on("GET", f"{BASE}{HOME}/charger/plan/query-plan",
               {"switchOn": 0, "plans": REAL_PLANS},
               {"switchOn": 0, "plans": REAL_PLANS},
               lost, lost, lost,
               {"switchOn": 0, "plans": REAL_PLANS})
    session.on("POST", f"{BASE}{HOME}/charger/plan/config-plan", FakeResponse())
    with pytest.raises(CommandNotConfirmed, match="restored"):
        client.set_schedule_enabled("NE=charger", True)
    sent = session.posted(f"{BASE}{HOME}/charger/plan/config-plan")
    assert [s["switchOn"] for s in sent] == [1, 0]
    assert api.plan_signature(sent[1]["plans"]) == api.plan_signature(REAL_PLANS)
