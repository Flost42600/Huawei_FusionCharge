"""Serve the FusionSolar captcha image to the config flow dialog.

The image is shown to the user, who types it. Nothing here solves it.
Each image gets a random, single-purpose token and expires after a few minutes.
The view needs no Home Assistant login because an <img> tag sends no token;
the 256-bit random URL is what protects it.
"""

from __future__ import annotations

import secrets
import time

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import KEY_HASS

from .const import CAPTCHA_TTL, CAPTCHA_VIEW_URL, DOMAIN

_DATA_KEY = f"{DOMAIN}_captcha_images"


def _store(hass: HomeAssistant) -> dict[str, tuple[float, bytes]]:
    return hass.data.setdefault(_DATA_KEY, {})


def register_captcha(hass: HomeAssistant, image: bytes) -> str:
    """Keep the image and return the URL that serves it."""
    store = _store(hass)
    now = time.monotonic()
    for token in [t for t, (exp, _) in store.items() if exp < now]:
        store.pop(token, None)
    if not hass.data.get(f"{_DATA_KEY}_view"):
        hass.http.register_view(CaptchaView())
        hass.data[f"{_DATA_KEY}_view"] = True
    token = secrets.token_urlsafe(32)
    store[token] = (now + CAPTCHA_TTL, image)
    return CAPTCHA_VIEW_URL.format(token=token)


def drop_captchas(hass: HomeAssistant) -> None:
    _store(hass).clear()


def _content_type(image: bytes) -> str:
    if image.startswith(b"\x89PNG"):
        return "image/png"
    if image.startswith(b"GIF8"):
        return "image/gif"
    return "image/jpeg"


class CaptchaView(HomeAssistantView):
    """GET /api/huawei_fusioncharge/captcha/{token}."""

    url = CAPTCHA_VIEW_URL
    name = f"api:{DOMAIN}:captcha"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        entry = _store(hass).get(token)
        if entry is None or entry[0] < time.monotonic():
            return web.Response(status=404)
        return web.Response(
            body=entry[1],
            content_type=_content_type(entry[1]),
            headers={"Cache-Control": "no-store"},
        )
