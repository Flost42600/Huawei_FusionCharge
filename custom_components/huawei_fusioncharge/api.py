"""Blocking client for the Huawei FusionSolar cloud, limited to one SCharger.

Login flow adapted from FusionSolarPlus (GPL v3). Charger endpoints were captured
from the FusionSolar app by the FusionSolarPlus fork of Matthias2703
(branch feature/charger-control). None of them is documented by Huawei.

Scope, on purpose:
  * read: real-time values, working mode (signal 20002), schedule switch and plans;
  * write: start / stop charging, arm the schedule, working mode, schedule on/off.
The plans themselves are never edited: switching the schedule resends them
unchanged, because the cloud replaces the whole plan list on every write.

Every method blocks; Home Assistant runs them in the executor.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

from .encryption import encrypt_password, get_secure_random
from .exceptions import (
    AuthenticationError,
    CannotConnect,
    CaptchaRequired,
    CloudError,
    CommandNotConfirmed,
    FusionChargeError,
    InvalidCaptcha,
    NoActivePlan,
    UnsafeOperation,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = (10, 30)  # connect, read (seconds)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
)

MOC_TYPE_CHARGER = "60080"
MOC_ID_CONNECTOR = 60081
CONNECTOR_NUMBER = 1  # the SCharger has one gun, the app always sends 1

SIGNAL_WORKING_MODE = 20002
WORKING_MODE_NORMAL = "0"
WORKING_MODE_PV = "1"
WORKING_MODES = (WORKING_MODE_NORMAL, WORKING_MODE_PV)

# Fields the cloud stores for a plan; a plan lacking one cannot be resent safely.
PLAN_REQUIRED_FIELDS = (
    "startTime",
    "stopTime",
    "chargeMode",
    "repeatPeriod",
    "maxChargePower",
    "isValid",
    "isRepeat",
)
# Fields the app adds when sending; they are derived from the stored ones.
PLAN_DERIVED_FIELDS = ("calculatedStartTime", "calculatedStopTime", "repeat", "valid")

MIN_SECONDS_BETWEEN_WRITES = 3.0
VERIFY_CHECKS = 3
VERIFY_PAUSE = 3.0
PLAN_READ_PAUSE = 1.0
RETRY_PAUSE = 2.0

_sleep = time.sleep  # patched in tests


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true")


def normalize_subdomain(subdomain: str) -> str:
    """Accept 'uni004eu5', 'uni004eu5.fusionsolar.huawei.com' or a full URL."""
    value = subdomain.strip().lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/", 1)[0]
    suffix = ".fusionsolar.huawei.com"
    while value.endswith(suffix):
        value = value[: -len(suffix)]
    if not re.fullmatch(r"[a-z0-9-]+", value or ""):
        raise ValueError(f"Invalid FusionSolar subdomain: {subdomain!r}")
    return value


@dataclass
class Signal:
    """One signal of get-realtime-info."""

    value: Any  # text as shown in the app, or None
    real: float | None  # numeric value when the cloud gives one
    unit: str | None = None


@dataclass
class ChargerIds:
    """The two cloud ids of a charger: connector (mode) and charger (schedule)."""

    connector: int
    charger: int


@dataclass
class ChargerState:
    """Everything the coordinator holds for one charger."""

    connector: dict[int, Signal] = field(default_factory=dict)
    charger: dict[int, Signal] = field(default_factory=dict)
    working_mode: str | None = None
    schedule_on: bool | None = None
    plan_count: int | None = None
    plans: list[dict] | None = None
    plan_meta: dict | None = None  # query-plan fields other than the plans
    device_meta: dict | None = None  # device-tree fields of the connector (connection status)
    control_read: bool = False  # True when the values above were read this time


class FusionChargeClient:
    """Session and requests for one FusionSolar account."""

    def __init__(
        self,
        username: str,
        password: str,
        subdomain: str,
        session: requests.Session | None = None,
    ) -> None:
        self._user = username
        self._password = password
        self._subdomain = normalize_subdomain(subdomain)
        if self._subdomain.startswith("region"):
            self._login_subdomain = self._subdomain[8:]
        elif self._subdomain.startswith("uni"):
            self._login_subdomain = self._subdomain[6:]
        else:
            self._login_subdomain = self._subdomain
        self._session = session or _new_session()
        self._lock = threading.RLock()
        self._company_dn: str | None = None
        self._pending_region: str | None = None  # multi-region step awaiting a captcha
        self._ids: dict[str, ChargerIds] = {}
        self._last_write = 0.0

    # ------------------------------------------------------------------ helpers

    @property
    def subdomain(self) -> str:
        return self._subdomain

    @property
    def _base(self) -> str:
        return f"https://{self._subdomain}.fusionsolar.huawei.com"

    @property
    def _login_base(self) -> str:
        return f"https://{self._login_subdomain}.fusionsolar.huawei.com"

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        try:
            response = self._session.request(method, url, **kwargs)
        except requests.RequestException as err:
            raise CannotConnect(f"{method} {_path(url)} failed: {type(err).__name__}") from err
        if response.status_code >= 500:
            # Huawei often answers 500 with its reason in a JSON body: show it.
            reason = _error_reason(response)
            if reason:
                raise CloudError(
                    f"{method} {_path(url)} returned HTTP {response.status_code}: {reason}"
                )
            raise CannotConnect(f"{method} {_path(url)} returned HTTP {response.status_code}")
        return response

    def _json(self, response: requests.Response) -> Any:
        """Parsed body; raises on HTTP errors and on error bodies.

        The cloud sometimes answers HTTP 200 with the failure inside the body,
        and a successful write often has an empty body.
        """
        if response.status_code >= 400:
            reason = _error_reason(response)
            raise CloudError(
                f"HTTP {response.status_code} on {_path(response.url)}"
                + (f": {reason}" if reason else "")
            )
        if not response.content:
            return None
        try:
            body = response.json()
        except ValueError:
            return None
        if isinstance(body, dict):
            if "exceptionId" in body:
                raise CloudError(f"cloud error {body['exceptionId']}")
            if "code" in body and str(body["code"]) != "0":
                raise CloudError(
                    f"cloud error code {body['code']}: {body.get('description') or ''}".strip()
                )
        return body

    # -------------------------------------------------------------------- login

    def login(self, verify_code: str | None = None) -> None:
        """Log in. Raises CaptchaRequired with the image when Huawei wants one.

        Call again with the typed `verify_code` and the same client: the captcha
        is bound to the session cookies of the first call.
        """
        with self._lock:
            if verify_code is None:
                self._session = _new_session()
                self._pending_region = None
                self._raise_if_captcha_shown()
            else:
                self._submit_captcha(verify_code.strip())

            if self._is_intl():
                self._login_intl(verify_code)
            elif self._pending_region is not None:
                region, self._pending_region = self._pending_region, None
                self._validate_user(region=region, verify_code=verify_code)
            else:
                self._validate_user(region=None, verify_code=verify_code)
            self._after_login()

    def _is_intl(self) -> bool:
        return self._subdomain in ("intl", "la5")

    def _captcha_image(self) -> bytes:
        r = self._request(
            "GET",
            f"{self._login_base}/unisso/verifycode",
            params={"timestamp": round(time.time() * 1000)},
        )
        if r.status_code >= 400 or not r.content:
            raise CannotConnect("Could not download the captcha image")
        return r.content

    def _raise_if_captcha_shown(self) -> None:
        r = self._request("GET", f"{self._login_base}/unisso/config")
        body = self._json(r) or {}
        if isinstance(body, dict) and body.get("showVerifyCode"):
            raise CaptchaRequired(self._captcha_image())

    def _submit_captcha(self, code: str) -> None:
        r = self._request(
            "POST",
            f"{self._login_base}/unisso/preValidVerifycode",
            data={"verifycode": code, "index": 0},
        )
        if r.status_code >= 400 or r.text.strip() != "success":
            raise InvalidCaptcha(self._captcha_image(), "Captcha refused")

    def _login_payload(self, region: str | None, verify_code: str | None) -> tuple[str, dict, dict]:
        r = self._request("GET", f"{self._login_base}/unisso/pubkey")
        if r.status_code != 200:
            raise CannotConnect(f"pubkey returned HTTP {r.status_code}")
        key_data = r.json()
        params: dict[str, Any] = {}
        password = self._password
        if key_data.get("enableEncrypt"):
            url = f"{self._login_base}/unisso/v3/validateUser.action"
            params["timeStamp"] = key_data["timeStamp"]
            params["nonce"] = get_secure_random()
            password = encrypt_password(key_data, password)
        else:
            url = f"{self._login_base}/unisso/v2/validateUser.action"
            params["decision"] = 1
            params["service"] = (
                f"{self._base}/unisess/v1/auth?service=/netecowebext/home/index.html#/LOGIN"
            )
        body: dict[str, Any] = {
            "organizationName": "",
            "username": self._user,
            "password": password,
        }
        if region:
            body["multiRegionName"] = region
        if verify_code:
            body["verifycode"] = verify_code
        return url, params, body

    def _validate_user(self, region: str | None, verify_code: str | None) -> None:
        url, params, body = self._login_payload(region, verify_code)
        r = self._request("POST", url, params=params, json=body)
        if r.status_code >= 400:
            raise AuthenticationError(f"Login refused (HTTP {r.status_code})")
        try:
            response = r.json()
        except ValueError as err:
            raise AuthenticationError("Unreadable login response") from err

        if str(response.get("errorCode")) == "470":
            multi = response.get("respMultiRegionName") or []
            target = multi[1] if len(multi) > 1 else None
            if region is None and isinstance(target, str) and not target.startswith("/"):
                # The account lives in another region: second request with its name.
                region = _multi_region_name(self._subdomain)
                r_cfg = self._json(self._request("GET", f"{self._login_base}/unisso/config")) or {}
                if r_cfg.get("showVerifyCode"):
                    self._pending_region = region
                    raise CaptchaRequired(self._captcha_image())
                self._validate_user(region=region, verify_code=None)
                return
            if isinstance(target, str) and target.startswith("/"):
                self._json(self._request("GET", f"{self._login_base}{target}"))
                return

        error = response.get("errorMsg")
        if error:
            if "verification code" in str(error).lower():
                image = self._captcha_image()
                if verify_code:
                    raise InvalidCaptcha(image, "Captcha refused")
                raise CaptchaRequired(image)
            raise AuthenticationError(str(error))

    def _login_intl(self, verify_code: str | None) -> None:
        r = self._request(
            "POST",
            f"{self._base}/rest/dp/uidm/unisso/v1/validate-user",
            params={"service": "/"},
            json={
                "username": self._user,
                "password": self._password,
                "verifycode": verify_code or "",
            },
            headers={"App-Id": "smartpvms"},
        )
        try:
            body = r.json()
        except ValueError as err:
            raise AuthenticationError("Unreadable login response") from err
        if body.get("code") != 0:
            message = (body.get("payload") or {}).get("exceptionMessage") or "login refused"
            if "verification code" in str(message).lower():
                raise CaptchaRequired(self._captcha_image())
            raise AuthenticationError(str(message))
        redirect = (body.get("payload") or {}).get("redirectURL")
        if redirect:
            if redirect.startswith("/"):
                redirect = f"{self._base}{redirect}"
            self._request("GET", redirect, allow_redirects=False)

    def _after_login(self) -> None:
        if not self._keep_alive():
            raise AuthenticationError("Login failed: no session after login")
        r = self._request(
            "GET",
            f"{self._base}/rest/neteco/web/organization/v2/company/current",
            params={"_": round(time.time() * 1000)},
        )
        if r.status_code in (400, 500) or not r.text.strip().startswith('{"data":'):
            raise AuthenticationError(
                "Unexpected answer after login: check the FusionSolar subdomain"
            )
        self._company_dn = r.json()["data"]["moDn"]

    def _keep_alive(self) -> bool:
        """Refresh the session and the CSRF token (header 'roarand')."""
        r = self._request("GET", f"{self._base}/rest/dpcloud/auth/v1/keep-alive")
        try:
            body = r.json()
        except ValueError:
            return False
        if body.get("code") != 0:
            return False
        if body.get("payload"):
            self._session.headers["roarand"] = body["payload"]
        return True

    def _session_alive(self) -> bool:
        r = self._request("GET", f"{self._base}/rest/dpcloud/auth/v1/is-session-alive")
        try:
            return r.json().get("code") == 0
        except ValueError:
            return False

    def ensure_session(self) -> None:
        """Keep the session alive, or log in again (may raise CaptchaRequired)."""
        with self._lock:
            if self._company_dn and self._session_alive() and self._keep_alive():
                return
            _LOGGER.debug("FusionSolar session expired, logging in again")
            self.login()

    # ---------------------------------------------------- session persistence

    def export_session(self) -> dict[str, Any] | None:
        """Cookies, CSRF token and company id, to survive a Home Assistant restart."""
        with self._lock:
            if not self._company_dn:
                return None
            return {
                "subdomain": self._subdomain,
                "company_dn": self._company_dn,
                "roarand": self._session.headers.get("roarand"),
                "cookies": [
                    {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                    for c in self._session.cookies
                ],
            }

    def import_session(self, data: dict[str, Any] | None) -> bool:
        """Load a saved session; ensure_session() then checks it is still alive."""
        if not data or data.get("subdomain") != self._subdomain or not data.get("cookies"):
            return False
        with self._lock:
            session = _new_session()
            for cookie in data["cookies"]:
                session.cookies.set(
                    cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path") or "/"
                )
            if data.get("roarand"):
                session.headers["roarand"] = data["roarand"]
            self._session = session
            self._company_dn = data.get("company_dn")
            return True

    def logout(self) -> None:
        try:
            self._request(
                "GET", f"{self._base}/unisess/v1/logout", params={"service": self._base}
            )
        except FusionChargeError:
            pass

    # ---------------------------------------------------------------- discovery

    def list_chargers(self) -> list[dict[str, str]]:
        """Chargers of the account: [{"dn": ..., "name": ...}]."""
        with self._lock:
            self.ensure_session()
            r = self._request(
                "GET",
                f"{self._base}/rest/neteco/web/config/device/v1/device-list",
                params={
                    "conditionParams.parentDn": self._company_dn,
                    "conditionParams.mocTypes": MOC_TYPE_CHARGER,
                    "_": round(time.time() * 1000),
                },
            )
            body = self._json(r) or {}
            chargers = []
            for device in body.get("data") or []:
                dn = device.get("dn")
                if not dn:
                    continue
                chargers.append(
                    {"dn": dn, "name": device.get("name") or device.get("devName") or dn}
                )
            return chargers

    def _get_ids(self, dn: str) -> ChargerIds:
        if dn in self._ids:
            return self._ids[dn]
        body = self._json(
            self._request(
                "POST",
                f"{self._base}/rest/dp/pvms/organization/v1/tree",
                json={
                    "parentDn": dn,
                    "treeDepth": "device",
                    "pageParam": {"needPage": True},
                    "filterCond": {"nameType": "device", "mocIdInclude": [MOC_ID_CONNECTOR]},
                    "displayCond": {"self": False, "status": True},
                },
            )
        )
        children = (body or {}).get("childList") if isinstance(body, dict) else None
        if not children:
            raise CloudError("No charging connector found for this charger")
        if len(children) > 1:
            _LOGGER.warning("Charger has %d connectors, only the first one is used", len(children))
        try:
            connector = int(children[0]["elementId"])
        except (KeyError, TypeError, ValueError) as err:
            raise CloudError("Connector without a usable id") from err

        body = self._json(
            self._request(
                "GET",
                f"{self._base}/rest/pvms/web/device/v1/mo-details",
                params={"dn": dn, "_": round(time.time() * 1000)},
            )
        )
        try:
            charger = int(((body or {}).get("data") or {}).get("mo", {})["dnId"])
        except (KeyError, TypeError, ValueError, AttributeError) as err:
            raise CloudError("Charger without a usable dnId") from err

        self._ids[dn] = ChargerIds(connector=connector, charger=charger)
        return self._ids[dn]

    # -------------------------------------------------------------------- reads

    def get_state(self, dn: str, include_control: bool = True) -> ChargerState:
        """Real-time values, plus working mode and schedule when asked.

        A network hiccup is retried once after a short pause before giving up.
        """
        try:
            return self._get_state(dn, include_control)
        except CannotConnect as err:
            _LOGGER.debug("Read failed (%s), retrying once", err)
            _sleep(RETRY_PAUSE)
            return self._get_state(dn, include_control)

    def _get_state(self, dn: str, include_control: bool) -> ChargerState:
        with self._lock:
            self.ensure_session()
            ids = self._get_ids(dn)
            state = ChargerState()
            raw = self._json(
                self._request(
                    "POST",
                    f"{self._base}/rest/neteco/web/homemgr/v1/device/get-realtime-info",
                    json={
                        "conditions": [
                            {"dnId": ids.connector, "queryAll": True},
                            {"dnId": ids.charger, "queryAll": True},
                        ]
                    },
                )
            )
            state.connector, state.charger = _split_realtime(raw, ids)
            if include_control:
                # Best effort: a failed control read leaves the values unknown
                # (entities unavailable) without taking the real-time ones down.
                try:
                    state.working_mode = self._read_working_mode(ids)
                    plan = self._query_plan(ids)
                    state.schedule_on = _truthy(plan["switchOn"])
                    plans = plan.get("plans")
                    state.plans = plans if isinstance(plans, list) else None
                    state.plan_count = len(plans) if isinstance(plans, list) else None
                    state.plan_meta = {k: v for k, v in plan.items() if k != "plans"}
                    state.control_read = True
                except CloudError as err:
                    _LOGGER.warning("Could not read the working mode or schedule: %s", err)
                try:
                    state.device_meta = self._read_device_meta(dn)
                except CloudError as err:
                    _LOGGER.debug("Could not read the device tree: %s", err)
            return state

    def _read_working_mode(self, ids: ChargerIds) -> str | None:
        body = self._json(
            self._request(
                "POST",
                f"{self._base}/rest/neteco/web/homemgr/v1/device/get-config-info",
                json={
                    "conditions": [
                        {"dnId": ids.connector, "queryAll": False, "signals": [SIGNAL_WORKING_MODE]}
                    ],
                    "verbose": True,
                },
            )
        )
        for signals in (body or {}).values() if isinstance(body, dict) else []:
            if not isinstance(signals, list):
                continue
            for signal in signals:
                try:
                    if int(signal.get("id")) == SIGNAL_WORKING_MODE and signal.get("value") is not None:
                        return str(signal["value"])
                except (TypeError, ValueError):
                    continue
        return None

    def _read_device_meta(self, dn: str) -> dict | None:
        """Scalar fields of the connector in the device tree (its connection status lives there)."""
        body = self._json(
            self._request(
                "POST",
                f"{self._base}/rest/dp/pvms/organization/v1/tree",
                json={
                    "parentDn": dn,
                    "treeDepth": "device",
                    "pageParam": {"needPage": True},
                    "filterCond": {"nameType": "device", "mocIdInclude": [MOC_ID_CONNECTOR]},
                    "displayCond": {"self": False, "status": True},
                },
            )
        )
        children = (body or {}).get("childList") if isinstance(body, dict) else None
        if not children or not isinstance(children[0], dict):
            return None
        return {
            k: v
            for k, v in children[0].items()
            if isinstance(v, (str, int, float, bool)) and k not in ("elementId", "elementDn", "dn", "parentDn")
        }

    def _query_plan(self, ids: ChargerIds) -> dict:
        body = self._json(
            self._request(
                "GET",
                f"{self._base}/rest/neteco/web/homemgr/v1/charger/plan/query-plan",
                params={"dnId": ids.charger},
            )
        )
        if not isinstance(body, dict) or "switchOn" not in body:
            # Fail closed: a missing switchOn must never read as "schedule off".
            raise CloudError("query-plan returned no switchOn")
        return body

    # ------------------------------------------------------------------- writes

    def _throttle(self) -> None:
        wait = MIN_SECONDS_BETWEEN_WRITES - (time.monotonic() - self._last_write)
        if wait > 0:
            _sleep(wait)
        self._last_write = time.monotonic()

    def set_working_mode(self, dn: str, mode: str) -> None:
        """Signal 20002: "0" normal charge, "1" PV power preferred. Confirmed by read-back."""
        if mode not in WORKING_MODES:
            raise ValueError(f"Invalid working mode {mode!r}")
        with self._lock:
            self.ensure_session()
            ids = self._get_ids(dn)
            if self._read_working_mode(ids) == mode:
                return
            for attempt in (1, 2):
                self._throttle()
                self._json(
                    self._request(
                        "POST",
                        f"{self._base}/rest/neteco/web/homemgr/v1/device/set-config-info",
                        json={
                            "changeValues": [{"id": str(SIGNAL_WORKING_MODE), "value": mode}],
                            "dnId": ids.connector,
                        },
                    )
                )
                if self._wait_for(lambda: self._read_working_mode(ids) == mode):
                    _LOGGER.info("Working mode set to %s", mode)
                    return
                _LOGGER.warning("Working mode not confirmed (attempt %d/2)", attempt)
            raise CommandNotConfirmed(f"The working mode still does not read {mode}")

    def _command(self, dn: str, action: str, payload: dict) -> Any:
        with self._lock:
            self.ensure_session()
            ids = self._get_ids(dn)
            self._throttle()
            body = self._json(
                self._request(
                    "POST",
                    f"{self._base}/rest/neteco/web/homemgr/v1/charger/{action}",
                    json={**payload, "dnId": ids.charger},
                )
            )
            status = body.get("chargeStatus") if isinstance(body, dict) else None
            _LOGGER.info("Charger command %s sent (chargeStatus=%s)", action, status)
            return status

    def start_charging(self, dn: str) -> Any:
        """The app's "Charge now": starts on connector 1, ignoring the plans."""
        return self._command(dn, "charge/start-charge", {"accountId": "", "gunNumber": CONNECTOR_NUMBER})

    def stop_charging(self, dn: str) -> Any:
        """The app's stop button."""
        return self._command(
            dn,
            "charge/stop-charge",
            {"gunNumber": CONNECTOR_NUMBER, "orderNumber": None, "serialNumber": None},
        )

    def arm_schedule(self, dn: str) -> Any:
        """The app's "Schedule" button: the charger waits for the plans (chargeStatus 10)."""
        return self._command(
            dn, "auth/confirm-auth", {"accountId": "", "authType": 0, "gunNumber": CONNECTOR_NUMBER}
        )

    def set_schedule_enabled(
        self,
        dn: str,
        enabled: bool,
        backup: Callable[[list[dict], bool], None] | None = None,
    ) -> None:
        """Switch the schedule on/off, resending the existing plans unchanged.

        config-plan replaces the whole plan list, so nothing is written unless two
        reads agree on a complete list of repeating plans. The plans are handed to
        `backup` first and compared field by field afterwards; if they do not come
        back unchanged, one restore attempt is made.
        """
        with self._lock:
            self.ensure_session()
            ids = self._get_ids(dn)
            first = self._query_plan(ids)
            if _truthy(first["switchOn"]) == enabled:
                return
            _sleep(PLAN_READ_PAUSE)
            second = self._query_plan(ids)
            for body in (first, second):
                if not isinstance(body.get("plans"), list):
                    raise UnsafeOperation("query-plan returned no plan list")
            if _truthy(first["switchOn"]) != _truthy(second["switchOn"]) or plan_signature(
                first["plans"]
            ) != plan_signature(second["plans"]):
                raise UnsafeOperation("The plans changed between two reads")
            stored = second["plans"]
            was_on = _truthy(second["switchOn"])
            plans, finished = split_finished_one_time_plans(stored, int(time.time() * 1000))
            check_plans_can_be_resent(plans, enabling=enabled)

            _LOGGER.info("Plans before switching the schedule: %s", json.dumps(stored))
            if finished:
                _LOGGER.info("Leaving out %d finished one-time plan(s)", len(finished))
            if backup is not None:
                try:
                    backup(stored, was_on)
                except Exception as err:  # noqa: BLE001 - a backup failure must not block
                    _LOGGER.error("Could not store the plan backup: %r", err)

            self._throttle()
            try:
                self._write_plans(ids, plans, enabled)
            except FusionChargeError as err:
                # Refused by the cloud: make sure nothing was half-written.
                _LOGGER.warning(
                    "config-plan refused (%s). Request sent: %s",
                    err,
                    json.dumps(self._plan_request(ids, plans, enabled)),
                )
                if self._wait_for(lambda: self._plans_match(ids, plans, was_on)):
                    hint = (
                        " (a charge is in progress or planned: switch Charge off first)"
                        if any(is_one_time(p) for p in plans)
                        else ""
                    )
                    raise CommandNotConfirmed(
                        f"the cloud refused the change ({err}); the plans are unchanged{hint}"
                    ) from err
                _LOGGER.error("Plans differ after a refused write, restoring them")
                self._throttle()
                self._write_plans(ids, plans, was_on)
                restored = self._wait_for(lambda: self._plans_match(ids, plans, was_on))
                raise CommandNotConfirmed(
                    f"the cloud refused the change ({err}); "
                    + ("the previous plans were restored" if restored else
                       "check the plans in the FusionSolar app (backup in .storage)")
                ) from err
            if self._wait_for(lambda: self._plans_match(ids, plans, enabled)):
                _LOGGER.info("Schedule switched %s", "on" if enabled else "off")
                return

            _LOGGER.error("Plans differ after the write, restoring the previous plans")
            restored = False
            try:
                self._throttle()
                self._write_plans(ids, plans, was_on)
                restored = self._wait_for(lambda: self._plans_match(ids, plans, was_on))
            except FusionChargeError as err:
                _LOGGER.error("Restoring the plans failed: %r", err)
            raise CommandNotConfirmed(
                "The schedule did not switch; "
                + (
                    "the previous plans were restored"
                    if restored
                    else "restoring failed, check the plans in the FusionSolar app "
                    "(they are in the log and in the backup)"
                )
            )

    @staticmethod
    def _plan_request(ids: ChargerIds, plans: list[dict], on: bool) -> dict:
        return {
            "plans": [plan_to_request(p) for p in plans],
            "switchOn": 1 if on else 0,
            "accountId": "",
            "dnId": ids.charger,
        }

    def _write_plans(self, ids: ChargerIds, plans: list[dict], on: bool) -> None:
        self._json(
            self._request(
                "POST",
                f"{self._base}/rest/neteco/web/homemgr/v1/charger/plan/config-plan",
                json=self._plan_request(ids, plans, on),
            )
        )

    def _plans_match(self, ids: ChargerIds, expected: list[dict], on: bool) -> bool:
        after = self._query_plan(ids)
        # One-time plans are left to the cloud (it may keep or drop finished ones).
        return _truthy(after["switchOn"]) == on and plan_signature(
            after.get("plans"), repeating_only=True
        ) == plan_signature(expected, repeating_only=True)

    def _wait_for(self, check: Callable[[], bool]) -> bool:
        for _ in range(VERIFY_CHECKS):
            _sleep(VERIFY_PAUSE)
            try:
                if check():
                    return True
            except FusionChargeError as err:
                _LOGGER.warning("Read-back failed: %r", err)
        return False


# ----------------------------------------------------------------- pure helpers


def _error_reason(response: Any) -> str | None:
    """Huawei's reason from an error body (exceptionId, descArgs, message), shortened."""
    try:
        body = response.json()
    except (ValueError, AttributeError):
        text = (getattr(response, "text", "") or "").strip()
        return text[:200] if text and not text.startswith("<") else None
    if not isinstance(body, dict):
        return None
    parts = [
        str(body[key])
        for key in ("exceptionId", "descArgs", "message", "description", "errorMsg", "code")
        if body.get(key) not in (None, "", [])
    ]
    return " | ".join(parts)[:300] if parts else None


def _path(url: str) -> str:
    """URL without host or query, for logs."""
    return re.sub(r"^https?://[^/]+", "", url or "").split("?", 1)[0]


def _multi_region_name(subdomain: str) -> str:
    name = subdomain[:-3] if subdomain.endswith("eu5") else subdomain
    if name.startswith("region") and name != "region05":
        name = re.sub(r"(region0?)(\d{1,2})", lambda m: f"region{int(m.group(2)):03d}", name)
    return name


def _to_signal(raw: dict) -> Signal:
    value = raw.get("value")
    if value in ("-", "N/A", "n/a", ""):
        value = None
    real: float | None
    try:
        real = float(raw.get("realValue"))
        if real != real or real in (float("inf"), float("-inf")):
            real = None
    except (TypeError, ValueError):
        real = None
    return Signal(value=value, real=real, unit=raw.get("unit"))


def _split_realtime(raw: Any, ids: ChargerIds) -> tuple[dict[int, Signal], dict[int, Signal]]:
    """Split get-realtime-info into connector and charger signals.

    The body is keyed by group; the group named after a dnId is used when present.
    Otherwise the group holding the connector-only signal 10004 is the connector.
    """
    groups: dict[str, dict[int, Signal]] = {}
    for key, signals in (raw or {}).items() if isinstance(raw, dict) else []:
        if not isinstance(signals, list):
            continue
        parsed: dict[int, Signal] = {}
        for item in signals:
            try:
                parsed[int(item.get("id"))] = _to_signal(item)
            except (TypeError, ValueError, AttributeError):
                continue
        groups[str(key)] = parsed

    connector = groups.get(str(ids.connector))
    charger = groups.get(str(ids.charger))
    if connector is None or charger is None:
        others = list(groups.values())
        connector = next((g for g in others if 10004 in g), {})
        charger = next((g for g in others if g is not connector), {})
    return connector, charger


def hhmm(value: str) -> int:
    """'07:30' -> 730, as the app sends calculatedStartTime."""
    hours, minutes = value[:5].split(":")
    return int(hours) * 100 + int(minutes)


def is_one_time(plan: dict) -> bool:
    """A one-time plan (isRepeat false) stores epoch milliseconds instead of HH:MM."""
    return not _truthy(plan.get("isRepeat"))


def _epoch_ms(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _utc_hhmm_from_ms(value: Any) -> int:
    seconds = (_epoch_ms(value) or 0) // 1000
    return (seconds // 3600 % 24) * 100 + seconds // 60 % 60


def plan_to_request(plan: dict) -> dict:
    """A stored plan rebuilt the way the app sends it."""
    if is_one_time(plan):
        start, stop = _utc_hhmm_from_ms(plan["startTime"]), _utc_hhmm_from_ms(plan["stopTime"])
    else:
        start, stop = hhmm(plan["startTime"]), hhmm(plan["stopTime"])
    return {
        **{k: v for k, v in plan.items() if k not in PLAN_DERIVED_FIELDS},
        "calculatedStartTime": start,
        "calculatedStopTime": stop,
        "repeat": plan.get("isRepeat"),
        "valid": plan.get("isValid"),
    }


def plan_signature(plans: list[dict] | None, repeating_only: bool = False) -> list[str]:
    """Order-independent fingerprint of every stored field."""
    return sorted(
        json.dumps({k: v for k, v in p.items() if k not in PLAN_DERIVED_FIELDS}, sort_keys=True)
        for p in plans or []
        if not (repeating_only and is_one_time(p))
    )


def split_finished_one_time_plans(plans: list[dict], now_ms: int) -> tuple[list[dict], list[dict]]:
    """(plans to resend, finished one-time plans to leave out).

    The cloud records a "Charge now" as a short one-time plan that stays in the
    list after it ends (seen on a SCharger-7KS-S0). A finished one is dropped
    when the list is written back; an ongoing or future one is kept.
    """
    keep, finished = [], []
    for plan in plans:
        end = _epoch_ms(plan.get("stopTime")) if is_one_time(plan) else None
        (finished if end is not None and end < now_ms else keep).append(plan)
    return keep, finished


def check_plans_can_be_resent(plans: list[dict], enabling: bool) -> None:
    """Refuse plans that cannot be reproduced exactly."""
    if enabling and not plans:
        raise UnsafeOperation("no plan is defined: create one in the FusionSolar app first")
    if enabling and not any(_truthy(p.get("isValid")) for p in plans):
        # The cloud answers "Charge plan parameters invalid" in this case (seen on a SCharger-7KS-S0).
        raise NoActivePlan(
            "every plan is unchecked: tick at least one plan in the FusionSolar app first"
        )
    for plan in plans:
        missing = [f for f in PLAN_REQUIRED_FIELDS if f not in plan]
        if missing:
            raise UnsafeOperation(f"A plan lacks {missing}: change the schedule in the app")
        if is_one_time(plan):
            if _epoch_ms(plan["startTime"]) is None or _epoch_ms(plan["stopTime"]) is None:
                raise UnsafeOperation("A one-time plan has an unexpected time format")
            continue
        try:
            hhmm(str(plan["startTime"]))
            hhmm(str(plan["stopTime"]))
        except (ValueError, IndexError) as err:
            raise UnsafeOperation("A plan has an unexpected time format") from err
