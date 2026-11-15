"""Exceptions raised by the FusionCharge cloud client."""

from __future__ import annotations


class FusionChargeError(Exception):
    """Base class for every error of this integration."""


class CannotConnect(FusionChargeError):
    """The FusionSolar cloud could not be reached (network, timeout, HTTP 5xx)."""


class AuthenticationError(FusionChargeError):
    """Username, password or region rejected."""


class CaptchaRequired(FusionChargeError):
    """Huawei asks for a captcha. The user has to type it; it is never solved automatically."""

    def __init__(self, image: bytes, message: str = "Captcha required") -> None:
        super().__init__(message)
        self.image = image


class InvalidCaptcha(CaptchaRequired):
    """The typed captcha was refused; `image` holds a fresh one."""


class CloudError(FusionChargeError):
    """The cloud answered, but with an error (often inside an HTTP 200 body)."""


class CommandNotConfirmed(FusionChargeError):
    """A write was accepted but reading it back did not show the requested value."""


class UnsafeOperation(FusionChargeError):
    """A write was refused locally because it could damage the user's settings."""
