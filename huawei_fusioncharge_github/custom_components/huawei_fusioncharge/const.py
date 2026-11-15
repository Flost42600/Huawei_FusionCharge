"""Constants for the Huawei FusionCharge integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "huawei_fusioncharge"
MANUFACTURER: Final = "Huawei"

CONF_SUBDOMAIN: Final = "subdomain"
CONF_CHARGER_DN: Final = "charger_dn"
CONF_CHARGER_NAME: Final = "charger_name"
CONF_CAPTCHA: Final = "captcha"

OPT_ENABLE_CONTROL: Final = "enable_control"
OPT_SCAN_INTERVAL: Final = "scan_interval"
OPT_CONTROL_INTERVAL: Final = "control_interval"

DEFAULT_ENABLE_CONTROL: Final = False
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds, real-time values
DEFAULT_CONTROL_INTERVAL: Final = 60  # seconds, working mode and schedule
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 600

# Real-time signals (ids from get-realtime-info, taken from FusionSolarPlus)
SIG_STATUS: Final = 10004
SIG_POWER: Final = 10013  # kW
SIG_SESSION_ENERGY: Final = 10035  # kWh
SIG_SESSION_DURATION: Final = 10036  # s
SIG_CURRENT_A: Final = 10032  # A
SIG_CONNECTION: Final = 19999
SIG_TOTAL_ENERGY: Final = 10008  # kWh, on the charger group
SIG_SOFTWARE: Final = 10001  # on the charger group
SIG_HARDWARE: Final = 10002  # on the charger group
SIG_MODEL: Final = 10007  # on the charger group

WORKING_MODE_OPTIONS: Final = ["normal", "pv_preferred"]  # signal 20002 = 0 / 1

STORAGE_VERSION: Final = 1
STORAGE_KEY_BACKUP: Final = f"{DOMAIN}_plan_backup"
BACKUP_KEEP: Final = 10

CAPTCHA_VIEW_URL: Final = f"/api/{DOMAIN}/captcha/{{token}}"
CAPTCHA_TTL: Final = 600  # seconds
