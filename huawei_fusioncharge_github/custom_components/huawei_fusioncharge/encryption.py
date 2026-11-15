"""RSA encryption of the FusionSolar password.

Adapted from FusionSolarPlus (https://github.com/JortvanSchijndel/FusionSolarPlus),
itself derived from fusion-solar-py. Licensed under the GNU GPL v3.
"""

from __future__ import annotations

import base64
import os
import urllib.parse

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .exceptions import FusionChargeError


def get_secure_random() -> str:
    """16 random bytes as hex, like the FusionSolar web page."""
    return os.urandom(16).hex()


def encrypt_password(key_data: dict, password: str) -> str:
    """Encrypt the password with the public key returned by /unisso/pubkey."""
    for field in ("enableEncrypt", "pubKey", "version"):
        if field not in key_data:
            raise FusionChargeError(f"Public key data lacks '{field}'")
    if not key_data["enableEncrypt"]:
        return password

    try:
        public_key = serialization.load_pem_public_key(
            key_data["pubKey"].encode(), backend=default_backend()
        )
    except Exception as err:  # noqa: BLE001 - any parsing failure is fatal here
        raise FusionChargeError("Could not load the FusionSolar public key") from err

    value = urllib.parse.quote(password)
    chunks = []
    for i in range(0, len(value) // 270 + 1):
        part = value[i * 270 : (i + 1) * 270]
        encrypted = public_key.encrypt(
            part.encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA384()),
                algorithm=hashes.SHA384(),
                label=None,
            ),
        )
        chunks.append(base64.b64encode(encrypted).decode("utf-8"))
    return "00000001".join(chunks) + key_data["version"]
